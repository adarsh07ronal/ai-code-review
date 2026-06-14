from typing import Optional
import httpx
import structlog
from app.core.config import settings

log = structlog.get_logger()

GITHUB_API = "https://api.github.com"


class GitHubService:

    # ── Webhook management ────────────────────────────────────────────────────

    async def install_webhook(self, access_token: str, full_name: str) -> Optional[int]:
        """Install our webhook on a GitHub repository. Returns webhook ID."""
        # In production use your real public URL; in dev use ngrok URL
        webhook_url = f"http://localhost:8000/api/v1/github/webhook"

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{GITHUB_API}/repos/{full_name}/hooks",
                json={
                    "name": "web",
                    "active": True,
                    "events": ["pull_request"],
                    "config": {
                        "url": webhook_url,
                        "content_type": "json",
                        "secret": settings.GITHUB_WEBHOOK_SECRET,
                    },
                },
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                },
                timeout=10,
            )

        if resp.status_code == 201:
            return resp.json()["id"]
        log.warning("Webhook install failed", status=resp.status_code, body=resp.text)
        return None

    async def uninstall_webhook(
        self, access_token: str, full_name: str, webhook_id: int
    ) -> bool:
        async with httpx.AsyncClient() as client:
            resp = await client.delete(
                f"{GITHUB_API}/repos/{full_name}/hooks/{webhook_id}",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                },
                timeout=10,
            )
        return resp.status_code == 204

    # ── Diff fetching ─────────────────────────────────────────────────────────

    async def get_pr_diff(self, access_token: str, full_name: str, pr_number: int) -> str:
        """Fetch the unified diff for a pull request."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{GITHUB_API}/repos/{full_name}/pulls/{pr_number}",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github.v3.diff",
                },
                timeout=30,
                follow_redirects=True,
            )
        resp.raise_for_status()
        return resp.text

    async def get_pr_files(self, access_token: str, full_name: str, pr_number: int) -> list:
        """Fetch list of files changed in a pull request."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{GITHUB_API}/repos/{full_name}/pulls/{pr_number}/files",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                },
                params={"per_page": 100},
                timeout=30,
            )
        resp.raise_for_status()
        return resp.json()

    async def post_review_comment(
        self,
        access_token: str,
        full_name: str,
        pr_number: int,
        body: str,
        event: str = "COMMENT",
    ) -> dict:
        """Post an AI review back to the GitHub PR."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{GITHUB_API}/repos/{full_name}/pulls/{pr_number}/reviews",
                json={"body": body, "event": event},
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                },
                timeout=15,
            )
        resp.raise_for_status()
        return resp.json()

    async def list_user_repos(self, access_token: str) -> list:
        """List repos the user has access to (for the connect repo UI)."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{GITHUB_API}/user/repos",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                },
                params={"sort": "updated", "per_page": 50, "type": "owner"},
                timeout=15,
            )
        resp.raise_for_status()
        return resp.json()

    # ── Review queue ──────────────────────────────────────────────────────────

    async def queue_review(self, pr_id: int):
        """
        Kick off the AI review pipeline for a PR as a background asyncio task.
        The worker runs independently so the webhook handler can return 200 immediately.
        """
        import asyncio
        from app.services.review_worker import review_worker

        log.info("Queuing PR for AI review", pr_id=pr_id)
        asyncio.create_task(review_worker.run(pr_id))


github_service = GitHubService()
