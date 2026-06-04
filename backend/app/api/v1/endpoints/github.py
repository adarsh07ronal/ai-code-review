import hashlib
import hmac as hmac_lib
import json
from fastapi import APIRouter, Depends, HTTPException, Request, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
import structlog

from app.core.config import settings
from app.core.dependencies import get_db
from app.models.review import Repository, PullRequest, PRStatus
from app.services.github_service import github_service

log = structlog.get_logger()
router = APIRouter(prefix="/github", tags=["GitHub"])


def verify_webhook_signature(payload: bytes, signature: str) -> bool:
    if not settings.GITHUB_WEBHOOK_SECRET:
        return True
    mac = hmac_lib.new(
        settings.GITHUB_WEBHOOK_SECRET.encode("utf-8"),
        msg=payload,
        digestmod=hashlib.sha256,
    )
    expected = "sha256=" + mac.hexdigest()
    return hmac_lib.compare_digest(expected, signature)


@router.post("/webhook")
async def github_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_github_event: Optional[str] = Header(None),
    x_hub_signature_256: Optional[str] = Header(None),
):
    payload_bytes = await request.body()
    if x_hub_signature_256:
        if not verify_webhook_signature(payload_bytes, x_hub_signature_256):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")
    payload = json.loads(payload_bytes)
    event = x_github_event or "unknown"
    log.info("GitHub webhook received", gh_event=event)
    if event == "ping":
        return {"message": "pong", "hook_id": payload.get("hook_id")}
    if event == "pull_request":
        await handle_pull_request_event(db, payload)
    return {"status": "ok", "event": event}


async def handle_pull_request_event(db: AsyncSession, payload: dict):
    action = payload.get("action")
    if action not in ("opened", "synchronize", "reopened"):
        return
    pr_data = payload["pull_request"]
    repo_data = payload["repository"]
    result = await db.execute(
        select(Repository).where(Repository.github_repo_id == repo_data["id"])
    )
    repo = result.scalar_one_or_none()
    if not repo:
        return
    existing = await db.execute(
        select(PullRequest).where(PullRequest.github_pr_id == pr_data["id"])
    )
    pr = existing.scalar_one_or_none()
    from datetime import datetime
    opened_at = datetime.fromisoformat(pr_data["created_at"].replace("Z", "+00:00"))
    if pr:
        pr.head_sha = pr_data["head"]["sha"]
        pr.status = PRStatus.PENDING
    else:
        pr = PullRequest(
            repository_id=repo.id,
            github_pr_number=pr_data["number"],
            github_pr_id=pr_data["id"],
            title=pr_data["title"],
            author_login=pr_data["user"]["login"],
            base_branch=pr_data["base"]["ref"],
            head_branch=pr_data["head"]["ref"],
            head_sha=pr_data["head"]["sha"],
            diff_url=pr_data.get("diff_url"),
            files_changed=pr_data.get("changed_files", 0),
            additions=pr_data.get("additions", 0),
            deletions=pr_data.get("deletions", 0),
            opened_at=opened_at,
            status=PRStatus.PENDING,
        )
        db.add(pr)
    await db.flush()
    await db.refresh(pr)
    await github_service.queue_review(pr.id)
