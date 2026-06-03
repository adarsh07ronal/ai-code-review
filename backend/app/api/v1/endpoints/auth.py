from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
import secrets

from app.core.dependencies import get_db, get_current_user
from app.core.security import decode_token, create_access_token
from app.core.config import settings
from app.schemas.auth import (
    TokenPair, LoginRequest, RefreshRequest,
    UserCreate, UserOut, GitHubCallbackRequest
)
from app.services.auth_service import auth_service

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/register", response_model=TokenPair, status_code=201)
async def register(data: UserCreate, db: AsyncSession = Depends(get_db)):
    """Register with email + password."""
    user = await auth_service.register(db, data)
    return auth_service.issue_tokens(user)


@router.post("/login", response_model=TokenPair)
async def login(data: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Login with email + password."""
    user = await auth_service.login(db, data.email, data.password)
    return auth_service.issue_tokens(user)


@router.post("/refresh", response_model=TokenPair)
async def refresh_token(data: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """Exchange a refresh token for a new token pair."""
    payload = decode_token(data.refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=400, detail="Invalid refresh token")
    from app.models.user import User
    from sqlalchemy import select
    result = await db.execute(select(User).where(User.id == int(payload["sub"])))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return auth_service.issue_tokens(user)


@router.get("/me", response_model=UserOut)
async def get_me(current_user=Depends(get_current_user)):
    """Return the currently authenticated user."""
    return current_user


# ── GitHub OAuth ─────────────────────────────────────────────────────────────

@router.get("/github")
async def github_oauth_redirect():
    """Redirect the browser to GitHub's OAuth authorization page."""
    state = secrets.token_urlsafe(16)
    params = (
        f"client_id={settings.GITHUB_CLIENT_ID}"
        f"&redirect_uri={settings.GITHUB_OAUTH_REDIRECT_URI}"
        f"&scope=user:email,repo"
        f"&state={state}"
    )
    return RedirectResponse(f"https://github.com/login/oauth/authorize?{params}")


@router.get("/github/callback")
async def github_callback(code: str, state: str = "", db: AsyncSession = Depends(get_db)):
    """GitHub redirects here after the user grants access."""
    user = await auth_service.github_login_or_register(db, code)
    tokens = auth_service.issue_tokens(user)
    # In production redirect to frontend with tokens in query or cookie
    frontend_redirect = (
        f"{settings.FRONTEND_URL}/auth/callback"
        f"?access_token={tokens['access_token']}"
        f"&refresh_token={tokens['refresh_token']}"
    )
    return RedirectResponse(url=frontend_redirect)


@router.post("/github/token", response_model=TokenPair)
async def github_token_exchange(
    data: GitHubCallbackRequest, db: AsyncSession = Depends(get_db)
):
    """API endpoint for SPA-style GitHub OAuth (frontend handles redirect)."""
    user = await auth_service.github_login_or_register(db, data.code)
    return auth_service.issue_tokens(user)
