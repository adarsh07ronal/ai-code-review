from datetime import datetime, timezone
from typing import Optional
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException, status

from app.models.user import User
from app.schemas.auth import UserCreate
from app.core.security import hash_password, verify_password, create_access_token, create_refresh_token
from app.core.config import settings


class AuthService:

    # ── Email / Password ──────────────────────────────────────────────────────

    async def register(self, db: AsyncSession, data: UserCreate) -> User:
        # Check uniqueness
        existing = await db.execute(
            select(User).where(
                (User.email == data.email) | (User.username == data.username)
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email or username already registered",
            )
        user = User(
            email=data.email,
            username=data.username,
            display_name=data.display_name or data.username,
            hashed_password=hash_password(data.password),
        )
        db.add(user)
        await db.flush()
        await db.refresh(user)
        return user

    async def login(self, db: AsyncSession, email: str, password: str) -> User:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if not user or not user.hashed_password:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )
        if not verify_password(password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )
        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")
        user.last_login_at = datetime.now(timezone.utc)
        await db.flush()
        return user

    # ── GitHub OAuth ─────────────────────────────────────────────────────────

    async def github_exchange_code(self, code: str) -> dict:
        """Exchange OAuth code for GitHub access token."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://github.com/login/oauth/access_token",
                json={
                    "client_id": settings.GITHUB_CLIENT_ID,
                    "client_secret": settings.GITHUB_CLIENT_SECRET,
                    "code": code,
                },
                headers={"Accept": "application/json"},
                timeout=10,
            )
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"GitHub OAuth error: {data.get('error_description', data['error'])}",
            )
        return data

    async def github_get_user(self, access_token: str) -> dict:
        """Fetch authenticated user profile from GitHub."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://api.github.com/user",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                },
                timeout=10,
            )
        resp.raise_for_status()
        return resp.json()

    async def github_get_primary_email(self, access_token: str) -> Optional[str]:
        """Fetch the primary verified email from GitHub."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://api.github.com/user/emails",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                },
                timeout=10,
            )
        if resp.status_code != 200:
            return None
        emails = resp.json()
        for e in emails:
            if e.get("primary") and e.get("verified"):
                return e["email"]
        return None

    async def github_login_or_register(self, db: AsyncSession, code: str) -> User:
        """Full GitHub OAuth flow: exchange code → get user → upsert in DB."""
        token_data = await self.github_exchange_code(code)
        access_token = token_data["access_token"]
        gh_user = await self.github_get_user(access_token)

        github_id = gh_user["id"]
        result = await db.execute(select(User).where(User.github_id == github_id))
        user = result.scalar_one_or_none()

        if user:
            # Update GitHub token on re-login
            user.github_access_token = access_token
            user.avatar_url = gh_user.get("avatar_url")
            user.last_login_at = datetime.now(timezone.utc)
        else:
            # New user — fetch email
            email = gh_user.get("email") or await self.github_get_primary_email(access_token)
            if not email:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="GitHub account has no public/verified email",
                )
            # Check if email is already used by an account without GitHub
            existing = await db.execute(select(User).where(User.email == email))
            if existing.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Email already registered. Please log in and connect GitHub in settings.",
                )
            username = gh_user.get("login", f"user{github_id}")
            # Ensure username uniqueness
            uname_result = await db.execute(select(User).where(User.username == username))
            if uname_result.scalar_one_or_none():
                username = f"{username}{github_id}"

            user = User(
                email=email,
                username=username,
                display_name=gh_user.get("name") or username,
                avatar_url=gh_user.get("avatar_url"),
                github_id=github_id,
                github_access_token=access_token,
                is_verified=True,
                last_login_at=datetime.now(timezone.utc),
            )
            db.add(user)

        await db.flush()
        await db.refresh(user)
        return user

    # ── Token helpers ─────────────────────────────────────────────────────────

    def issue_tokens(self, user: User) -> dict:
        return {
            "access_token": create_access_token(user.id),
            "refresh_token": create_refresh_token(user.id),
            "token_type": "bearer",
            "user": user,
        }


auth_service = AuthService()
