from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import (
    String, Boolean, DateTime, Text, ForeignKey, Integer,
    Enum as SAEnum, JSON, BigInteger
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.db.session import Base


class OrgRole(str, enum.Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


class PRStatus(str, enum.Enum):
    PENDING = "pending"
    REVIEWING = "reviewing"
    COMPLETED = "completed"
    FAILED = "failed"


class ReviewSeverity(str, enum.Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


# ── Organization ────────────────────────────────────────────────────────────

class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(200))
    github_org_id: Mapped[Optional[int]] = mapped_column(BigInteger, unique=True)
    stripe_customer_id: Mapped[Optional[str]] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    members: Mapped[List["OrganizationMember"]] = relationship(back_populates="organization")
    repositories: Mapped[List["Repository"]] = relationship(back_populates="organization")


class OrganizationMember(Base):
    __tablename__ = "organization_members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[OrgRole] = mapped_column(SAEnum(OrgRole), default=OrgRole.MEMBER)
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    organization: Mapped["Organization"] = relationship(back_populates="members")
    user: Mapped["User"] = relationship(back_populates="organizations")  # type: ignore[name-defined]


# ── Repository ───────────────────────────────────────────────────────────────

class Repository(Base):
    __tablename__ = "repositories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    github_repo_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    organization_id: Mapped[Optional[int]] = mapped_column(ForeignKey("organizations.id"))

    full_name: Mapped[str] = mapped_column(String(300), unique=True)  # "owner/repo"
    name: Mapped[str] = mapped_column(String(200))
    is_private: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)   # webhook installed
    default_branch: Mapped[str] = mapped_column(String(100), default="main")
    webhook_id: Mapped[Optional[int]] = mapped_column(BigInteger)

    # Review config stored as JSON: {"severity_threshold": "warning", "auto_post": true}
    review_config: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    owner: Mapped["User"] = relationship(back_populates="repositories")  # type: ignore[name-defined]
    organization: Mapped[Optional["Organization"]] = relationship(back_populates="repositories")
    pull_requests: Mapped[List["PullRequest"]] = relationship(
        back_populates="repository", cascade="all, delete-orphan"
    )


# ── Pull Request ─────────────────────────────────────────────────────────────

class PullRequest(Base):
    __tablename__ = "pull_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id"), index=True)

    github_pr_number: Mapped[int] = mapped_column(Integer)
    github_pr_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    title: Mapped[str] = mapped_column(Text)
    author_login: Mapped[str] = mapped_column(String(100))
    base_branch: Mapped[str] = mapped_column(String(200))
    head_branch: Mapped[str] = mapped_column(String(200))
    head_sha: Mapped[str] = mapped_column(String(40))

    status: Mapped[PRStatus] = mapped_column(SAEnum(PRStatus), default=PRStatus.PENDING, index=True)
    diff_url: Mapped[Optional[str]] = mapped_column(Text)
    files_changed: Mapped[int] = mapped_column(Integer, default=0)
    additions: Mapped[int] = mapped_column(Integer, default=0)
    deletions: Mapped[int] = mapped_column(Integer, default=0)

    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    repository: Mapped["Repository"] = relationship(back_populates="pull_requests")
    reviews: Mapped[List["CodeReview"]] = relationship(
        back_populates="pull_request", cascade="all, delete-orphan"
    )


# ── Code Review ───────────────────────────────────────────────────────────────

class CodeReview(Base):
    __tablename__ = "code_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    pull_request_id: Mapped[int] = mapped_column(ForeignKey("pull_requests.id"), index=True)

    # AI-generated summary and structured findings
    summary: Mapped[Optional[str]] = mapped_column(Text)
    findings: Mapped[Optional[dict]] = mapped_column(JSON)   # list of {file, line, severity, message}
    security_issues: Mapped[Optional[dict]] = mapped_column(JSON)
    architecture_suggestions: Mapped[Optional[dict]] = mapped_column(JSON)

    # Metrics
    critical_count: Mapped[int] = mapped_column(Integer, default=0)
    warning_count: Mapped[int] = mapped_column(Integer, default=0)
    info_count: Mapped[int] = mapped_column(Integer, default=0)
    tokens_used: Mapped[int] = mapped_column(Integer, default=0)

    # Was this review posted back to GitHub as a PR review?
    posted_to_github: Mapped[bool] = mapped_column(Boolean, default=False)
    github_review_id: Mapped[Optional[int]] = mapped_column(BigInteger)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    pull_request: Mapped["PullRequest"] = relationship(back_populates="reviews")
