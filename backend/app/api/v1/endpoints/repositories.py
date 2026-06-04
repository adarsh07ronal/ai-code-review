from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import List, Optional
import structlog

from app.core.dependencies import get_db, get_current_user
from app.models.user import User
from app.models.review import Repository, PullRequest
from app.services.github_service import github_service

log = structlog.get_logger()
router = APIRouter(prefix="/repositories", tags=["Repositories"])


class RepositoryOut(BaseModel):
    id: int
    full_name: str
    name: str
    is_private: bool
    is_active: bool
    default_branch: str
    model_config = {"from_attributes": True}


class ConnectRepoRequest(BaseModel):
    full_name: str          # "owner/repo"
    github_repo_id: int
    is_private: bool = False
    default_branch: str = "main"


@router.get("", response_model=List[RepositoryOut])
async def list_repositories(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all repositories connected by the current user."""
    result = await db.execute(
        select(Repository).where(Repository.owner_id == current_user.id)
    )
    return result.scalars().all()


@router.post("", response_model=RepositoryOut, status_code=201)
async def connect_repository(
    data: ConnectRepoRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Connect a GitHub repository and install the webhook."""
    if not current_user.github_access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GitHub account not connected. Please sign in with GitHub.",
        )

    # Check not already connected
    existing = await db.execute(
        select(Repository).where(Repository.github_repo_id == data.github_repo_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Repository already connected")

    # Install GitHub webhook
    webhook_id = await github_service.install_webhook(
        access_token=current_user.github_access_token,
        full_name=data.full_name,
    )

    repo = Repository(
        github_repo_id=data.github_repo_id,
        owner_id=current_user.id,
        full_name=data.full_name,
        name=data.full_name.split("/")[-1],
        is_private=data.is_private,
        default_branch=data.default_branch,
        webhook_id=webhook_id,
        is_active=True,
    )
    db.add(repo)
    await db.flush()
    await db.refresh(repo)
    log.info("Repository connected", full_name=data.full_name)
    return repo


@router.delete("/{repo_id}", status_code=204)
async def disconnect_repository(
    repo_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Disconnect a repository and uninstall the webhook."""
    result = await db.execute(
        select(Repository).where(
            Repository.id == repo_id,
            Repository.owner_id == current_user.id,
        )
    )
    repo = result.scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    if repo.webhook_id and current_user.github_access_token:
        await github_service.uninstall_webhook(
            access_token=current_user.github_access_token,
            full_name=repo.full_name,
            webhook_id=repo.webhook_id,
        )

    await db.delete(repo)
    log.info("Repository disconnected", full_name=repo.full_name)


@router.get("/{repo_id}/pull-requests")
async def list_pull_requests(
    repo_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all pull requests for a repository."""
    result = await db.execute(
        select(Repository).where(
            Repository.id == repo_id,
            Repository.owner_id == current_user.id,
        )
    )
    repo = result.scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    prs = await db.execute(
        select(PullRequest)
        .where(PullRequest.repository_id == repo_id)
        .order_by(PullRequest.opened_at.desc())
    )
    return prs.scalars().all()
