from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Vendor(Base):
    __tablename__ = "vendors"

    slug: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    spec_url: Mapped[str] = mapped_column(Text)
    old_spec_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    poll_interval_seconds: Mapped[int] = mapped_column(Integer, default=6 * 60 * 60)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_custom: Mapped[bool] = mapped_column(Boolean, default=False)
    tenant_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SpecSnapshot(Base):
    """A content-addressed spec version.

    ``digest`` is derived from ``content``, so ``(vendor_slug, digest)`` is
    unique and re-fetching an unchanged spec is a no-op. Snapshots are shared
    across api/worker/beat via the database rather than each process keeping a
    private copy on local disk.
    """

    __tablename__ = "spec_snapshots"
    __table_args__ = (
        UniqueConstraint("vendor_slug", "digest", name="uq_spec_snapshots_vendor_digest"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vendor_slug: Mapped[str] = mapped_column(
        String(64), ForeignKey("vendors.slug"), index=True
    )
    digest: Mapped[str] = mapped_column(String(16))
    etag: Mapped[str | None] = mapped_column(String(256), nullable=True)
    spec_format: Mapped[str] = mapped_column(String(8), default="json")
    content: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SpecPointer(Base):
    """A named pointer to a snapshot digest — e.g. ``latest`` or ``old``.

    Modelled as its own table so that moving one pointer cannot disturb
    another. The filesystem store conflated these: writing a snapshot always
    rewrote ``latest.json``, so pinning a baseline clobbered the latest pointer
    and discarded its ETag.
    """

    __tablename__ = "spec_pointers"

    vendor_slug: Mapped[str] = mapped_column(
        String(64), ForeignKey("vendors.slug"), primary_key=True
    )
    label: Mapped[str] = mapped_column(String(32), primary_key=True)
    digest: Mapped[str] = mapped_column(String(16))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DetectionRun(Base):
    __tablename__ = "detection_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vendor_slug: Mapped[str] = mapped_column(
        String(64), ForeignKey("vendors.slug"), index=True
    )
    tenant_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    old_digest: Mapped[str | None] = mapped_column(String(16), nullable=True)
    new_digest: Mapped[str | None] = mapped_column(String(16), nullable=True)
    breaking_count: Mapped[int] = mapped_column(Integer, default=0)
    additive_count: Mapped[int] = mapped_column(Integer, default=0)
    changes: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Repository(Base):
    __tablename__ = "repositories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    owner: Mapped[str] = mapped_column(String(128))
    name: Mapped[str] = mapped_column(String(128))
    vendor_slug: Mapped[str] = mapped_column(String(64), default="github")
    default_branch: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AppInstallation(Base):
    __tablename__ = "app_installations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    install_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    owner: Mapped[str] = mapped_column(String(128), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ChangelogEntry(Base):
    __tablename__ = "changelog_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vendor_slug: Mapped[str] = mapped_column(
        String(64), ForeignKey("vendors.slug"), index=True
    )
    tenant_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    run_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("detection_runs.id"), nullable=True, index=True
    )
    kind: Mapped[str] = mapped_column(String(16))
    path: Mapped[str] = mapped_column(Text)
    method: Mapped[str] = mapped_column(String(64))
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(256), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(256))
    tenant_id: Mapped[str] = mapped_column(String(128), index=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    key_hash: Mapped[str] = mapped_column(String(256), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    prefix: Mapped[str] = mapped_column(String(8))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    repository_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("repositories.id"), index=True
    )
    status: Mapped[str] = mapped_column(String(16), default="queued")
    current_step: Mapped[str | None] = mapped_column(String(32), nullable=True)
    task_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pr_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pr_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)