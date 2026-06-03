from typing import AsyncGenerator, Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token, CREDENTIALS_EXCEPTION
from app.db.session import AsyncSessionLocal
from app.db.redis import get_redis_client

security = HTTPBearer(auto_error=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async DB session, closing it after the request."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_redis():
    """Yield a Redis client."""
    return await get_redis_client()


async def get_current_user_id(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> int:
    """Extract and validate user ID from JWT Bearer token."""
    if not credentials:
        raise CREDENTIALS_EXCEPTION
    payload = decode_token(credentials.credentials)
    if payload.get("type") != "access":
        raise CREDENTIALS_EXCEPTION
    user_id = payload.get("sub")
    if not user_id:
        raise CREDENTIALS_EXCEPTION
    return int(user_id)


async def get_current_user(
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Load the current user from DB. Raises 401 if not found."""
    from app.models.user import User
    from sqlalchemy import select

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise CREDENTIALS_EXCEPTION
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user")
    return user
