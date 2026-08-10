from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SpecSnapshot(Base):
    __tablename__ = "spec_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vendor_slug: Mapped[str] = mapped_column(
        String(64), ForeignKey("vendors.slug"), index=True
    )
    digest: Mapped[str] = mapped_column(String(16))
    etag: Mapped[str | None] = mapped_column(String(256), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DetectionRun(Base):
    __tablename__ = "detection_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vendor_slug: Mapped[str] = mapped_column(
        String(64), ForeignKey("vendors.slug"), index=True
    )
    old_digest: Mapped[str | None] = mapped_column(String(16), nullable=True)
    new_digest: Mapped[str] = mapped_column(String(16))
    breaking_count: Mapped[int] = mapped_column(Integer, default=0)
    additive_count: Mapped[int] = mapped_column(Integer, default=0)
    changes: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)