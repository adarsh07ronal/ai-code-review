"""
Billing endpoint — Phase 5
Stripe Checkout for subscription upgrades, the customer billing portal, and
the webhook that keeps User.subscription_tier in sync with Stripe.
"""
from typing import Optional

import stripe
import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import get_current_user, get_db
from app.models.user import SubscriptionTier, User
from app.services.billing_service import billing_service

log = structlog.get_logger()
router = APIRouter(prefix="/billing", tags=["Billing"])


class CheckoutRequest(BaseModel):
    tier: str  # "pro" | "team"


class CheckoutResponse(BaseModel):
    checkout_url: str


class PortalResponse(BaseModel):
    portal_url: str


@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout(
    data: CheckoutRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if data.tier not in ("pro", "team"):
        raise HTTPException(status_code=400, detail="tier must be 'pro' or 'team'")

    customer_id = await billing_service.get_or_create_customer(
        existing_customer_id=current_user.stripe_customer_id,
        email=current_user.email,
        name=current_user.display_name or current_user.username,
    )
    if current_user.stripe_customer_id != customer_id:
        current_user.stripe_customer_id = customer_id
        await db.flush()

    checkout_url = await billing_service.create_checkout_session(
        customer_id=customer_id,
        tier=data.tier,
        success_url=f"{settings.FRONTEND_URL}/dashboard/billing?checkout=success",
        cancel_url=f"{settings.FRONTEND_URL}/dashboard/billing?checkout=cancelled",
    )
    return CheckoutResponse(checkout_url=checkout_url)


@router.post("/portal", response_model=PortalResponse)
async def create_portal(current_user: User = Depends(get_current_user)):
    if not current_user.stripe_customer_id:
        raise HTTPException(status_code=400, detail="No billing account yet")
    portal_url = await billing_service.create_portal_session(
        customer_id=current_user.stripe_customer_id,
        return_url=f"{settings.FRONTEND_URL}/dashboard/billing",
    )
    return PortalResponse(portal_url=portal_url)


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    stripe_signature: Optional[str] = Header(None, alias="Stripe-Signature"),
):
    payload = await request.body()
    try:
        event = billing_service.construct_webhook_event(payload, stripe_signature or "")
    except (ValueError, stripe.error.SignatureVerificationError):
        raise HTTPException(status_code=400, detail="Invalid Stripe webhook signature")

    log.info("Stripe webhook received", stripe_event_type=event["type"])
    obj = event["data"]["object"]
    customer_id = obj.get("customer")

    if event["type"] in ("checkout.session.completed", "customer.subscription.updated"):
        tier = (obj.get("metadata") or {}).get("tier")
        if customer_id and tier in ("pro", "team"):
            result = await db.execute(select(User).where(User.stripe_customer_id == customer_id))
            user = result.scalar_one_or_none()
            if user:
                user.subscription_tier = SubscriptionTier(tier)
                await db.flush()

    elif event["type"] == "customer.subscription.deleted":
        if customer_id:
            result = await db.execute(select(User).where(User.stripe_customer_id == customer_id))
            user = result.scalar_one_or_none()
            if user:
                user.subscription_tier = SubscriptionTier.FREE
                await db.flush()

    return {"status": "ok"}
