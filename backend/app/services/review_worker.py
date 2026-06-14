"""
Review Worker — Phase 3
Orchestrates the full pipeline for a single PR:
  1. Load PR + Repository from DB
  2. Fetch the unified diff from GitHub
  3. Run AI review (GPT-4o)
  4. Persist CodeReview to DB
  5. Post review comment back to GitHub PR
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionFactory
from app.models.review import CodeReview, PRStatus, PullRequest, Repository
from app.models.user import User
from app.services.ai_service import ai_service
from app.services.github_service import github_service

log = structlog.get_logger()


class ReviewWorker:
    """Executes the full review pipeline for one PR."""

    async def run(self, pr_id: int) -> None:
        """Entry point — creates its own DB session so it can run as a background task."""
        async with AsyncSessionFactory() as db:
            try:
                await self._process(db, pr_id)
                await db.commit()
            except Exception as exc:
                await db.rollback()
                log.error("Review pipeline failed", pr_id=pr_id, error=str(exc))
                # Mark the PR as FAILED so the UI can surface it
                await self._mark_failed(pr_id, str(exc))

    # ── Pipeline ──────────────────────────────────────────────────────────────

    async def _process(self, db: AsyncSession, pr_id: int) -> None:
        # 1. Load PR → Repository → owner User
        pr = await self._load_pr(db, pr_id)
        if pr is None:
            log.warning("PR not found — skipping review", pr_id=pr_id)
            return

        repo_result = await db.execute(
            select(Repository).where(Repository.id == pr.repository_id)
        )
        repo = repo_result.scalar_one_or_none()
        if repo is None:
            log.warning("Repository not found for PR", pr_id=pr_id)
            return

        owner_result = await db.execute(
            select(User).where(User.id == repo.owner_id)
        )
        owner = owner_result.scalar_one_or_none()
        if owner is None or not owner.github_access_token:
            log.warning("Repo owner has no GitHub token", repo=repo.full_name)
            return

        # 2. Mark as REVIEWING
        pr.status = PRStatus.REVIEWING
        await db.flush()

        log.info("Starting review", repo=repo.full_name, pr=pr.github_pr_number)

        # 3. Fetch the PR diff
        diff = await github_service.get_pr_diff(
            access_token=owner.github_access_token,
            full_name=repo.full_name,
            pr_number=pr.github_pr_number,
        )

        # 4. Run AI review
        review_data = await ai_service.review_pull_request(
            diff=diff,
            full_name=repo.full_name,
            pr_number=pr.github_pr_number,
            title=pr.title,
            author=pr.author_login,
            files_changed=pr.files_changed,
            additions=pr.additions,
            deletions=pr.deletions,
        )

        # 5. Count severities
        findings = review_data.get("findings", [])
        security = review_data.get("security_issues", [])
        critical = sum(1 for f in findings + security if f.get("severity") == "critical")
        warnings = sum(1 for f in findings + security if f.get("severity") in ("warning", "error"))
        infos    = sum(1 for f in findings if f.get("severity") == "info")

        # 6. Persist CodeReview
        code_review = CodeReview(
            pull_request_id=pr.id,
            summary=review_data.get("summary"),
            findings=findings,
            security_issues=security,
            architecture_suggestions=review_data.get("architecture_suggestions", []),
            critical_count=critical,
            warning_count=warnings,
            info_count=infos,
            tokens_used=review_data.get("tokens_used", 0),
        )
        db.add(code_review)
        await db.flush()
        await db.refresh(code_review)

        # 7. Post review back to GitHub (if enabled)
        config = repo.review_config or {}
        if config.get("auto_post", True):
            comment_body = self._format_github_comment(review_data, pr.github_pr_number)
            try:
                gh_resp = await github_service.post_review_comment(
                    access_token=owner.github_access_token,
                    full_name=repo.full_name,
                    pr_number=pr.github_pr_number,
                    body=comment_body,
                    event="COMMENT",
                )
                code_review.posted_to_github = True
                code_review.github_review_id = gh_resp.get("id")
                log.info("Review posted to GitHub", gh_review_id=gh_resp.get("id"))
            except Exception as exc:
                log.warning("Failed to post review to GitHub", error=str(exc))

        # 8. Mark PR as COMPLETED
        pr.status = PRStatus.COMPLETED
        log.info(
            "Review completed",
            pr_id=pr_id,
            critical=critical,
            warnings=warnings,
            tokens=review_data.get("tokens_used", 0),
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _load_pr(self, db: AsyncSession, pr_id: int) -> PullRequest | None:
        result = await db.execute(select(PullRequest).where(PullRequest.id == pr_id))
        return result.scalar_one_or_none()

    async def _mark_failed(self, pr_id: int, error: str) -> None:
        async with AsyncSessionFactory() as db:
            result = await db.execute(select(PullRequest).where(PullRequest.id == pr_id))
            pr = result.scalar_one_or_none()
            if pr:
                pr.status = PRStatus.FAILED
                await db.commit()

    def _format_github_comment(self, review_data: dict, pr_number: int) -> str:
        """Format the AI review as a readable GitHub PR comment (Markdown)."""
        lines: list[str] = []

        quality = review_data.get("overall_quality", "")
        quality_emoji = {"good": "✅", "needs_work": "⚠️", "major_issues": "🚨"}.get(quality, "🤖")

        lines.append(f"## {quality_emoji} AI Code Review")
        lines.append("")
        lines.append(f"**Overall quality:** `{quality}`")
        lines.append("")

        summary = review_data.get("summary", "")
        if summary:
            lines.append(f"> {summary}")
            lines.append("")

        findings = review_data.get("findings", [])
        if findings:
            lines.append("### 🔍 Findings")
            lines.append("")
            SEV_ICON = {"critical": "🔴", "error": "🟠", "warning": "🟡", "info": "🔵"}
            for f in findings:
                icon = SEV_ICON.get(f.get("severity", "info"), "⚪")
                file_ref = f.get("file", "")
                line_ref = f" (line {f['line']})" if f.get("line") else ""
                lines.append(f"- {icon} **{f.get('severity', '').upper()}** `{file_ref}`{line_ref}")
                lines.append(f"  {f.get('message', '')}")
                if f.get("suggestion"):
                    lines.append(f"  > 💡 {f['suggestion']}")
            lines.append("")

        security = review_data.get("security_issues", [])
        if security:
            lines.append("### 🔒 Security Issues")
            lines.append("")
            for s in security:
                cwe = f" ({s['cwe']})" if s.get("cwe") else ""
                lines.append(f"- 🚨 **{s.get('severity', '').upper()}**{cwe} `{s.get('file', '')}`")
                lines.append(f"  {s.get('issue', '')}")
                if s.get("remediation"):
                    lines.append(f"  > 🔧 {s['remediation']}")
            lines.append("")

        arch = review_data.get("architecture_suggestions", [])
        if arch:
            lines.append("### 🏗️ Architecture Suggestions")
            lines.append("")
            for a in arch:
                lines.append(f"- **{a.get('area', '')}**: {a.get('suggestion', '')}")
            lines.append("")

        lines.append("---")
        lines.append("*Generated by [AI Code Review](https://github.com) · Powered by GPT-4o*")

        return "\n".join(lines)


review_worker = ReviewWorker()
