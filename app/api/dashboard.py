"""Argus Dashboard - web UI for monitoring API changes and activity."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import DetectionRun, Repository
from app.db.repository import open_session
from app.registry.vendors import list_vendors

router = APIRouter(tags=["dashboard"])


def _from_request(request: Request) -> Settings:
    return request.app.state.settings


SettingsDep = Annotated[Settings, Depends(_from_request)]


def _safe_session(settings: Settings) -> Session | None:
    """Return a DB session or None if no database is configured."""
    if not settings.database_url:
        return None
    return open_session(settings)


@router.get("/dashboard")
def dashboard_index(request: Request, settings: SettingsDep) -> dict:
    """Main dashboard page with overview stats."""
    session = _safe_session(settings)
    vendors_data = []
    total_breaking = 0
    total_additive = 0
    recent_runs = []
    repositories = []

    try:
        if session is not None:
            # Vendor stats
            vendors = list_vendors(settings)
            for v in vendors:
                runs = session.execute(
                    select(DetectionRun)
                    .where(DetectionRun.vendor_slug == v.slug)
                    .order_by(DetectionRun.id.desc())
                    .limit(1)
                ).scalars().all()
                last_run = runs[0] if runs else None
                total_runs = session.execute(
                    select(func.count(DetectionRun.id))
                    .where(DetectionRun.vendor_slug == v.slug)
                ).scalar() or 0
                vendors_data.append({
                    "slug": v.slug,
                    "name": v.name,
                    "enabled": v.enabled,
                    "total_runs": total_runs,
                    "last_run_at": last_run.created_at if last_run else None,
                    "last_breaking": last_run.breaking_count if last_run else 0,
                    "last_additive": last_run.additive_count if last_run else 0,
                })

            # Overall stats
            stats = session.execute(
                select(
                    func.coalesce(func.sum(DetectionRun.breaking_count), 0),
                    func.coalesce(func.sum(DetectionRun.additive_count), 0),
                )
            ).one()
            total_breaking = stats[0]
            total_additive = stats[1]

            # Recent runs
            rows = session.execute(
                select(DetectionRun).order_by(DetectionRun.id.desc()).limit(10)
            ).scalars().all()
            recent_runs = [
                {
                    "id": r.id,
                    "vendor_slug": r.vendor_slug,
                    "breaking_count": r.breaking_count,
                    "additive_count": r.additive_count,
                    "created_at": r.created_at,
                }
                for r in rows
            ]

            # Repos
            repos = session.execute(
                select(Repository).order_by(Repository.id).limit(20)
            ).scalars().all()
            repositories = [
                {
                    "id": r.id,
                    "owner": r.owner,
                    "name": r.name,
                    "vendor_slug": r.vendor_slug,
                    "is_active": r.is_active,
                    "last_run_at": r.last_run_at,
                }
                for r in repos
            ]
    finally:
        if session is not None:
            session.close()

    return {
        "vendors": vendors_data,
        "total_breaking": total_breaking,
        "total_additive": total_additive,
        "recent_runs": recent_runs,
        "repositories": repositories,
        "total_vendors": len(vendors_data),
    }


@router.get("/dashboard/vendors")
def dashboard_vendors(request: Request, settings: SettingsDep) -> dict:
    """Vendor detail page with run history."""
    session = _safe_session(settings)
    vendors_data = []
    try:
        if session is not None:
            vendors = list_vendors(settings)
            for v in vendors:
                runs = session.execute(
                    select(DetectionRun)
                    .where(DetectionRun.vendor_slug == v.slug)
                    .order_by(DetectionRun.id.desc())
                    .limit(20)
                ).scalars().all()
                vendors_data.append({
                    "slug": v.slug,
                    "name": v.name,
                    "enabled": v.enabled,
                    "spec_url": v.spec_url,
                    "poll_interval_seconds": v.poll_interval_seconds,
                    "runs": [
                        {
                            "id": r.id,
                            "breaking_count": r.breaking_count,
                            "additive_count": r.additive_count,
                            "old_digest": r.old_digest[:8] if r.old_digest else None,
                            "new_digest": r.new_digest[:8] if r.new_digest else None,
                            "created_at": r.created_at,
                        }
                        for r in runs
                    ],
                })
    finally:
        if session is not None:
            session.close()
    return {"vendors": vendors_data}


@router.get("/dashboard/activity")
def dashboard_activity(
    request: Request,
    settings: SettingsDep,
    days: int = 30,
) -> dict:
    """Activity page with detection runs over time."""
    session = _safe_session(settings)
    runs_data = []
    daily_stats = []
    try:
        if session is not None:
            since = datetime.now(tz=UTC) - timedelta(days=days)
            runs = session.execute(
                select(DetectionRun)
                .where(DetectionRun.created_at >= since)
                .order_by(DetectionRun.created_at.desc())
                .limit(200)
            ).scalars().all()
            runs_data = [
                {
                    "id": r.id,
                    "vendor_slug": r.vendor_slug,
                    "breaking_count": r.breaking_count,
                    "additive_count": r.additive_count,
                    "created_at": r.created_at,
                }
                for r in runs
            ]

            # Aggregate by day
            day_map: dict[str, dict] = {}
            for r in runs:
                day = r.created_at.strftime("%Y-%m-%d") if r.created_at else "unknown"
                if day not in day_map:
                    day_map[day] = {"day": day, "breaking": 0, "additive": 0, "runs": 0}
                day_map[day]["breaking"] += r.breaking_count
                day_map[day]["additive"] += r.additive_count
                day_map[day]["runs"] += 1
            daily_stats = sorted(day_map.values(), key=lambda x: x["day"])
    finally:
        if session is not None:
            session.close()
    return {
        "runs": runs_data,
        "daily_stats": daily_stats,
        "days": days,
    }


@router.get("/dashboard/repositories")
def dashboard_repositories(request: Request, settings: SettingsDep) -> dict:
    """Repository list page."""
    session = _safe_session(settings)
    repositories = []
    try:
        if session is not None:
            repos = session.execute(
                select(Repository).order_by(Repository.id)
            ).scalars().all()
            repositories = [
                {
                    "id": r.id,
                    "owner": r.owner,
                    "name": r.name,
                    "vendor_slug": r.vendor_slug,
                    "default_branch": r.default_branch,
                    "is_active": r.is_active,
                    "last_run_at": r.last_run_at,
                    "created_at": r.created_at,
                }
                for r in repos
            ]
    finally:
        if session is not None:
            session.close()
    return {"repositories": repositories}
