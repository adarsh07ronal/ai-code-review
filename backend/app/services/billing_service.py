"""
Stripe billing — Phase 5
Wraps Checkout, the customer billing portal, and webhook verification for
subscription upgrades. The tier is carried in Checkout/Subscription metadata
rather than derived from the price ID, so the webhook handler doesn't need
to keep an inverse price->tier map in sync with Stripe dashboard changes.
"""
from __future__ import annotations

from typing import Optional

import stripe
from fastapi.concurrency import run_in_threadpool

from app.core.config import settings

stripe.api_key = settings.STRIPE_SECRET_KEY

TIER_TO_PRICE = {
    "pro": settings.STRIPE_PRICE_ID_PRO,
    "team": settings.STRIPE_PRICE_ID_TEAM,
}


class BillingService:
    async def get_or_create_customer(
        self, *, existing_customer_id: Optional[str], email: str, name: str
    ) -> str:
        if existing_customer_id:
            return existing_customer_id
        customer = await run_in_threadpool(stripe.Customer.create, email=email, name=name)
        return customer.id

    async def create_checkout_session(
        self, *, customer_id: str, tier: str, success_url: str, cancel_url: str
    ) -> str:
        price_id = TIER_TO_PRICE.get(tier)
        if not price_id:
            raise ValueError(f"Unknown subscription tier: {tier}")
        session = await run_in_threadpool(
            stripe.checkout.Session.create,
            customer=customer_id,
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            metadata={"tier": tier},
            subscription_data={"metadata": {"tier": tier}},
            success_url=success_url,
            cancel_url=cancel_url,
        )
        return session.url

    async def create_portal_session(self, *, customer_id: str, return_url: str) -> str:
        session = await run_in_threadpool(
            stripe.billing_portal.Session.create,
            customer=customer_id,
            return_url=return_url,
        )
        return session.url

    def construct_webhook_event(self, payload: bytes, sig_header: str) -> stripe.Event:
        return stripe.Webhook.construct_event(payload, sig_header, settings.STRIPE_WEBHOOK_SECRET)


billing_service = BillingService()
