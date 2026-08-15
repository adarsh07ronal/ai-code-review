"""
Organizations endpoint — Phase 5
Multi-tenant teams: create an org, invite members, manage roles. This is
what backs the "team" subscription tier's collaboration features.
"""
from typing import List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_db, get_org_membership, require_org_role
from app.models.review import Organization, OrganizationMember, OrgRole
from app.models.user import User

log = structlog.get_logger()
router = APIRouter(prefix="/organizations", tags=["Organizations"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class OrganizationOut(BaseModel):
    id: int
    name: str
    display_name: Optional[str]
    model_config = {"from_attributes": True}


class OrganizationCreate(BaseModel):
    name: str
    display_name: Optional[str] = None


class MemberOut(BaseModel):
    user_id: int
    username: str
    email: str
    role: OrgRole


class MemberInvite(BaseModel):
    email: str
    role: OrgRole = OrgRole.MEMBER


class MemberRoleUpdate(BaseModel):
    role: OrgRole


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("", response_model=List[OrganizationOut])
async def list_my_organizations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Organizations the current user belongs to — backs the team switcher."""
    result = await db.execute(
        select(Organization)
        .join(OrganizationMember, OrganizationMember.organization_id == Organization.id)
        .where(OrganizationMember.user_id == current_user.id)
    )
    return result.scalars().all()


@router.post("", response_model=OrganizationOut, status_code=201)
async def create_organization(
    data: OrganizationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(select(Organization).where(Organization.name == data.name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Organization name already taken")

    org = Organization(name=data.name, display_name=data.display_name or data.name)
    db.add(org)
    await db.flush()
    await db.refresh(org)

    db.add(OrganizationMember(organization_id=org.id, user_id=current_user.id, role=OrgRole.OWNER))
    await db.flush()
    log.info("Organization created", name=org.name, owner_id=current_user.id)
    return org


@router.get("/{org_id}/members", response_model=List[MemberOut])
async def list_members(
    org_id: int,
    db: AsyncSession = Depends(get_db),
    _membership=Depends(get_org_membership),
):
    result = await db.execute(
        select(OrganizationMember, User)
        .join(User, User.id == OrganizationMember.user_id)
        .where(OrganizationMember.organization_id == org_id)
    )
    return [
        MemberOut(user_id=user.id, username=user.username, email=user.email, role=member.role)
        for member, user in result.all()
    ]


@router.post("/{org_id}/members", response_model=MemberOut, status_code=201)
async def invite_member(
    org_id: int,
    data: MemberInvite,
    db: AsyncSession = Depends(get_db),
    _membership=Depends(require_org_role(OrgRole.OWNER, OrgRole.ADMIN)),
):
    if data.role == OrgRole.OWNER:
        raise HTTPException(status_code=400, detail="Cannot invite a member directly as owner")

    user_result = await db.execute(select(User).where(User.email == data.email))
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="No user with that email")

    existing = await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == org_id,
            OrganizationMember.user_id == user.id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="User is already a member")

    db.add(OrganizationMember(organization_id=org_id, user_id=user.id, role=data.role))
    await db.flush()
    return MemberOut(user_id=user.id, username=user.username, email=user.email, role=data.role)


@router.patch("/{org_id}/members/{user_id}", response_model=MemberOut)
async def update_member_role(
    org_id: int,
    user_id: int,
    data: MemberRoleUpdate,
    db: AsyncSession = Depends(get_db),
    _membership=Depends(require_org_role(OrgRole.OWNER)),
):
    result = await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == org_id,
            OrganizationMember.user_id == user_id,
        )
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    if member.role == OrgRole.OWNER:
        raise HTTPException(status_code=400, detail="Cannot change the owner's role")

    member.role = data.role
    await db.flush()

    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one()
    return MemberOut(user_id=user.id, username=user.username, email=user.email, role=member.role)


@router.delete("/{org_id}/members/{user_id}", status_code=204)
async def remove_member(
    org_id: int,
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _membership=Depends(require_org_role(OrgRole.OWNER, OrgRole.ADMIN)),
):
    result = await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == org_id,
            OrganizationMember.user_id == user_id,
        )
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    if member.role == OrgRole.OWNER:
        raise HTTPException(status_code=400, detail="Cannot remove the organization owner")

    await db.delete(member)
