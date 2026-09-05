"""Argus Dashboard - web UI for monitoring API drift and activity."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select

from app.core.config import Settings
from app.db.models import DriftAlert, Repository
from app.db.repository import open_session
from app.registry.vendors import list_vendors

router = APIRouter(tags=["dashboard"])


def _from_request(request: Request) -> Settings:
    return request.app.state.settings


SettingsDep = Annotated[Settings, Depends(_from_request)]


@router.get("/api/v1/dashboard/stats")
def dashboard_stats(settings: SettingsDep):

    session = open_session(settings)
    try:
        vendors = list_vendors(settings)
        vendor_stats = []
        for v in vendors:
            alert_count = session.execute(
                select(func.count(DriftAlert.id))
                .where(DriftAlert.vendor_slug == v.slug)
            ).scalar() or 0
            open_alerts = session.execute(
                select(func.count(DriftAlert.id))
                .where(
                    DriftAlert.vendor_slug == v.slug,
                    DriftAlert.resolved.is_(False),
                )
            ).scalar() or 0
            repo_count = session.execute(
                select(func.count(Repository.id))
                .where(
                    Repository.vendor_slug == v.slug,
                    Repository.is_active.is_(True),
                )
            ).scalar() or 0
            vendor_stats.append({
                "slug": v.slug,
                "name": v.name,
                "enabled": v.enabled,
                "total_alerts": alert_count,
                "open_alerts": open_alerts,
                "repositories": repo_count,
            })

        total_repos = session.execute(
            select(func.count(Repository.id)).where(Repository.is_active.is_(True))
        ).scalar() or 0
        total_open = session.execute(
            select(func.count(DriftAlert.id)).where(DriftAlert.resolved.is_(False))
        ).scalar() or 0

        return {
            "total_repos": total_repos,
            "total_open_alerts": total_open,
            "vendors": vendor_stats,
        }
    finally:
        session.close()


@router.get("/api/v1/dashboard/activity")
def dashboard_activity(settings: SettingsDep, limit: int = 20):
    session = open_session(settings)
    try:
        alerts = session.execute(
            select(DriftAlert)
            .order_by(DriftAlert.created_at.desc())
            .limit(limit)
        ).scalars().all()

        return [
            {
                "id": a.id,
                "vendor_slug": a.vendor_slug,
                "alert_type": a.alert_type,
                "severity": a.severity,
                "endpoint": a.endpoint,
                "resolved": a.resolved,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in alerts
        ]
    finally:
        session.close()
