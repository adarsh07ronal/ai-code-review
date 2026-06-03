from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime
from app.models.user import SubscriptionTier


# ── User ─────────────────────────────────────────────────────────────────────

class UserBase(BaseModel):
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$")
    display_name: Optional[str] = None


class UserCreate(UserBase):
    password: str = Field(..., min_length=8, max_length=72)


class UserOut(UserBase):
    id: int
    avatar_url: Optional[str]
    subscription_tier: SubscriptionTier
    is_verified: bool
    github_id: Optional[int]
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Auth ─────────────────────────────────────────────────────────────────────

class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserOut


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class GitHubCallbackRequest(BaseModel):
    code: str
    state: Optional[str] = None
