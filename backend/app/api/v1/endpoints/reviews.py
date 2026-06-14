"""
Reviews endpoint — Phase 3
Exposes CodeReview data so the frontend dashboard can display results.
"""
from typing import List, Optional, Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from datetime import datetime

from app.core.dependencies import get_db, get_current_user
from app.models.user import User
from app.models.review import CodeReview, PullRequest, Repository, PRStatus

router = APIRouter(prefix="/reviews", tags=["Reviews"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class CodeReviewOut(BaseModel):
    id: int
    pull_request_id: int
    summary: Optional[str]
    findings: Optional[Any]
    security_issues: Optional[Any]
    architecture_suggestions: Optional[Any]
    critical_count: int
    warning_count: int
    info_count: int
    tokens_used: int
    posted_to_github: bool
    github_review_id: Optional[int]
    created_at: datetime
    model_config = {"from_attributes": True}


class PullRequestWithReview(BaseModel):
    id: int
    github_pr_number: int
    title: str
    author_login: str
    base_branch: str
    head_branch: str
    status: PRStatus
    files_changed: int
    additions: int
    deletions: int
    opened_at: datetime
    reviews: List[CodeReviewOut] = []
    model_config = {"from_attributes": True}


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/pull-requests/{pr_id}", response_model=PullRequestWithReview)
async def get_pull_request_review(
    pr_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a pull request and all its AI reviews."""
    # Verify the PR belongs to a repo owned by the current user
    pr_result = await db.execute(
        select(PullRequest).where(PullRequest.id == pr_id)
    )
    pr = pr_result.scalar_one_or_none()
    if not pr:
        raise HTTPException(status_code=404, detail="Pull request not found")

    repo_result = await db.execute(
        select(Repository).where(
            Repository.id == pr.repository_id,
            Repository.owner_id == current_user.id,
        )
    )
    if not repo_result.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="Not authorised")

    # Load reviews
    reviews_result = await db.execute(
        select(CodeReview)
        .where(CodeReview.pull_request_id == pr_id)
        .order_by(CodeReview.created_at.desc())
    )
    reviews = reviews_result.scalars().all()

    return PullRequestWithReview(
        id=pr.id,
        github_pr_number=pr.github_pr_number,
        title=pr.title,
        author_login=pr.author_login,
        base_branch=pr.base_branch,
        head_branch=pr.head_branch,
        status=pr.status,
        files_changed=pr.files_changed,
        additions=pr.additions,
        deletions=pr.deletions,
        opened_at=pr.opened_at,
        reviews=[CodeReviewOut.model_validate(r) for r in reviews],
    )


@router.get("/repositories/{repo_id}/summary")
async def get_repository_review_summary(
    repo_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Summary stats for a repository: total PRs reviewed, issue counts, etc.
    Used by the dashboard overview cards.
    """
    repo_result = await db.execute(
        select(Repository).where(
            Repository.id == repo_id,
            Repository.owner_id == current_user.id,
        )
    )
    repo = repo_result.scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    # Fetch all PRs for this repo
    prs_result = await db.execute(
        select(PullRequest).where(PullRequest.repository_id == repo_id)
    )
    prs = prs_result.scalars().all()
    pr_ids = [p.id for p in prs]

    if not pr_ids:
        return {
            "repo_id": repo_id,
            "full_name": repo.full_name,
            "total_prs": 0,
            "reviewed_prs": 0,
            "pending_prs": 0,
            "total_critical": 0,
            "total_warnings": 0,
            "total_info": 0,
            "total_tokens_used": 0,
        }

    # Fetch all code reviews for those PRs
    reviews_result = await db.execute(
        select(CodeReview).where(CodeReview.pull_request_id.in_(pr_ids))
    )
    reviews = reviews_result.scalars().all()

    completed = sum(1 for p in prs if p.status == PRStatus.COMPLETED)
    pending   = sum(1 for p in prs if p.status == PRStatus.PENDING)

    return {
        "repo_id": repo_id,
        "full_name": repo.full_name,
        "total_prs": len(prs),
        "reviewed_prs": completed,
        "pending_prs": pending,
        "total_critical": sum(r.critical_count for r in reviews),
        "total_warnings": sum(r.warning_count for r in reviews),
        "total_info": sum(r.info_count for r in reviews),
        "total_tokens_used": sum(r.tokens_used for r in reviews),
    }
