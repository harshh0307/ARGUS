from __future__ import annotations

from app.core.config import get_settings
from app.db.models import Repository
from app.db.repository import (
    list_active_repositories,
    open_session,
    persist_detection,
    touch_repository,
    upsert_repository,
)
from app.registry.vendors import get_vendor, list_vendors
from app.services.pipeline import detect_changes, run_repo_pipeline


def run_detection(vendor_slug: str = "github") -> dict:
    settings = get_settings()
    vendor = get_vendor(settings, vendor_slug)
    result = detect_changes(settings, vendor_slug)
    if settings.database_url:
        persist_detection(settings, vendor_slug, result, vendor)
    return {
        "vendor": vendor_slug,
        "breaking_count": result.get("breaking_count", 0),
        "additive_count": result.get("additive_count", 0),
        "baselined": result.get("baselined", False),
        "changes": result.get("changes", []),
    }


def scan_and_fix(repository_id: int, merge: bool = True) -> dict:
    settings = get_settings()
    session = open_session(settings)
    try:
        repo = session.get(Repository, repository_id)
        if repo is None:
            return {"repository_id": repository_id, "error": "repo row not found"}
        owner, name = repo.owner, repo.name
    finally:
        session.close()

    outcome = run_repo_pipeline(
        settings,
        owner,
        name,
        branch="argus/fix",
        merge=merge,
    )
    result = outcome.pr_result
    return {
        "repository_id": repository_id,
        "owner": owner,
        "name": name,
        "pr_number": result.pr_number if result else None,
        "pr_url": result.pr_url if result else None,
        "passed": result.passed if result else None,
        "attempts": result.attempts if result else 0,
        "merged": outcome.merged,
        "merge_error": outcome.merge_error,
        "impacted": len(outcome.impacts),
    }


def register_repository(owner: str, name: str, default_branch: str | None = None) -> int:
    settings = get_settings()
    session = open_session(settings)
    try:
        repo = upsert_repository(session, owner, name, default_branch)
        session.commit()
        return repo.id
    finally:
        session.close()


def poll_all_vendors() -> dict:
    settings = get_settings()
    summary: dict[str, dict] = {}
    for vendor in list_vendors(settings):
        if not vendor.enabled:
            continue
        summary[vendor.slug] = run_detection(vendor.slug)
    return summary


def _sync_active_repos_and_dispatch() -> dict:
    settings = get_settings()
    session = open_session(settings)
    try:
        repos = list_active_repositories(session)
        results = {}
        for repo in repos:
            touch_repository(session, repo)
            results[f"{repo.owner}/{repo.name}"] = {
                "repository_id": repo.id,
                "active": repo.is_active,
            }
        session.commit()
        return results
    finally:
        session.close()