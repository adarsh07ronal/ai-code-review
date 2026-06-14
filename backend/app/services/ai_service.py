"""
AI Review Service — Phase 3
Calls GPT-4o with a PR diff and returns structured code review findings.
"""
from __future__ import annotations

import json
import re
import structlog
from openai import AsyncOpenAI

from app.core.config import settings

log = structlog.get_logger()

# ── Prompts ───────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are an expert software engineer performing a thorough code review.
You will receive a unified diff of a pull request. Your job is to analyse it and return
a structured JSON review with the following top-level keys:

{
  "summary": "<2-4 sentence plain-English overview of the PR>",
  "findings": [
    {
      "file": "<path/to/file.ext>",
      "line": <integer or null>,
      "severity": "<info|warning|error|critical>",
      "category": "<correctness|security|performance|style|maintainability|testing>",
      "message": "<concise description of the issue>",
      "suggestion": "<how to fix it>"
    }
  ],
  "security_issues": [
    {
      "file": "<path>",
      "line": <integer or null>,
      "severity": "<warning|error|critical>",
      "issue": "<description>",
      "cwe": "<CWE-xxx or null>",
      "remediation": "<how to fix>"
    }
  ],
  "architecture_suggestions": [
    {
      "area": "<brief label>",
      "suggestion": "<actionable recommendation>"
    }
  ],
  "overall_quality": "<good|needs_work|major_issues>"
}

Rules:
- Return ONLY valid JSON — no markdown fences, no prose before or after.
- If a section has nothing to report, use an empty list [].
- Keep each message under 200 characters.
- Focus on bugs, security flaws, and meaningful code quality issues — skip trivial nits unless severity is info.
- Line numbers refer to the *new* file (+ lines in the diff).
"""

USER_PROMPT_TEMPLATE = """\
Repository: {full_name}
PR #{pr_number}: {title}
Author: {author}
Files changed: {files_changed}  Additions: +{additions}  Deletions: -{deletions}

--- DIFF ---
{diff}
--- END DIFF ---
"""

# Rough token guard — GPT-4o context is 128k but we keep costs sane
MAX_DIFF_CHARS = 60_000


class AIService:
    def __init__(self) -> None:
        self._client: AsyncOpenAI | None = None

    @property
    def client(self) -> AsyncOpenAI:
        if self._client is None:
            self._client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        return self._client

    # ── Public API ────────────────────────────────────────────────────────────

    async def review_pull_request(
        self,
        *,
        diff: str,
        full_name: str,
        pr_number: int,
        title: str,
        author: str,
        files_changed: int,
        additions: int,
        deletions: int,
    ) -> dict:
        """
        Send a PR diff to GPT-4o and return a structured review dict.
        Keys: summary, findings, security_issues, architecture_suggestions, overall_quality, tokens_used
        """
        if not settings.OPENAI_API_KEY:
            log.warning("OPENAI_API_KEY not set — returning stub review")
            return self._stub_review()

        # Truncate oversized diffs with a notice
        truncated = False
        if len(diff) > MAX_DIFF_CHARS:
            diff = diff[:MAX_DIFF_CHARS]
            truncated = True
            log.warning("Diff truncated for AI review", chars=MAX_DIFF_CHARS)

        user_prompt = USER_PROMPT_TEMPLATE.format(
            full_name=full_name,
            pr_number=pr_number,
            title=title,
            author=author,
            files_changed=files_changed,
            additions=additions,
            deletions=deletions,
            diff=diff,
        )
        if truncated:
            user_prompt += "\n\n[NOTE: diff was truncated due to size — review may be incomplete]"

        try:
            response = await self.client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,        # low temp for consistent, factual output
                max_tokens=4096,
                response_format={"type": "json_object"},
            )
        except Exception as exc:
            log.error("OpenAI API call failed", error=str(exc))
            raise

        raw = response.choices[0].message.content or "{}"
        tokens_used = response.usage.total_tokens if response.usage else 0

        review = self._parse_response(raw)
        review["tokens_used"] = tokens_used
        log.info(
            "AI review complete",
            full_name=full_name,
            pr_number=pr_number,
            findings=len(review.get("findings", [])),
            security_issues=len(review.get("security_issues", [])),
            tokens=tokens_used,
        )
        return review

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _parse_response(self, raw: str) -> dict:
        """Parse JSON from the model, with a fallback for malformed output."""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # Try to extract JSON block if the model slipped in prose
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group())
                except json.JSONDecodeError:
                    data = {}
            else:
                data = {}

        return {
            "summary": data.get("summary", "Review could not be parsed."),
            "findings": data.get("findings", []),
            "security_issues": data.get("security_issues", []),
            "architecture_suggestions": data.get("architecture_suggestions", []),
            "overall_quality": data.get("overall_quality", "needs_work"),
        }

    def _stub_review(self) -> dict:
        """Returned when OPENAI_API_KEY is absent (dev/test mode)."""
        return {
            "summary": "Stub review: OpenAI API key not configured.",
            "findings": [
                {
                    "file": "N/A",
                    "line": None,
                    "severity": "info",
                    "category": "style",
                    "message": "This is a stub finding — configure OPENAI_API_KEY for real reviews.",
                    "suggestion": "Set OPENAI_API_KEY in your .env file.",
                }
            ],
            "security_issues": [],
            "architecture_suggestions": [],
            "overall_quality": "needs_work",
            "tokens_used": 0,
        }


ai_service = AIService()
