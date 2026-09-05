from __future__ import annotations

import threading

from app.core.config import get_settings
from app.db.models import Repository
from app.db.repository import (
    list_active_repos_for_vendor,
    list_installations,
    open_session,
    upsert_repository,
)
from app.github.client import GitHubApiError, GitHubClient
from app.registry.vendors import list_vendors
from app.services.pipeline import scan_changes, fix_directory


def run_repo_pipeline(settings, owner, name, *, branch="main", merge=True, vendor_slug="github", repository_id=None):
    from types import SimpleNamespace
    return SimpleNamespace(
        pr_result=SimpleNamespace(pr_number=None, pr_url=None, passed=False, attempts=0, failure=None),
        merged=False,
        merge_error=None,
        impacts=[],
    )

_celery_app = None


def _get_celery_app():
    global _celery_app
    if _celery_app is None:
        try:
            from app.workers.celery_app import app as _celery_app
        except Exception:  # noqa: BLE001, S110
            pass
    return _celery_app


def detect_changes(settings, vendor_slug: str = "github") -> dict:
    return {
        "vendor": vendor_slug,
        "breaking_count": 0,
        "additive_count": 0,
        "changes": [],
        "baselined": False,
    }


def run_detection(vendor_slug: str = "github") -> dict:
    settings = get_settings()
    result = detect_changes(settings, vendor_slug)
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
        vendor_slug = repo.vendor_slug
    finally:
        session.close()

    try:
        outcome = run_repo_pipeline(
            settings,
            owner,
            name,
            branch="argus/fix",
            merge=merge,
            vendor_slug=vendor_slug,
            repository_id=repository_id,
        )
    except (GitHubApiError, OSError, ValueError) as exc:
        return {
            "repository_id": repository_id,
            "owner": owner,
            "name": name,
            "error": f"pipeline failed: {type(exc).__name__}: {str(exc)[:500]}",
        }
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


def register_repository(
    owner: str,
    name: str,
    default_branch: str | None = None,
    vendor_slug: str = "github",
) -> int:
    settings = get_settings()
    session = open_session(settings)
    try:
        repo = upsert_repository(session, owner, name, default_branch, vendor_slug)
        session.commit()
        return repo.id
    finally:
        session.close()


def dispatch_scan_for_vendor(vendor_slug: str, breaking_count: int = 0) -> dict:
    """After detection finds breaking changes, scan all repos that use this vendor."""
    if breaking_count == 0:
        return {"dispatched": 0}
    settings = get_settings()
    session = open_session(settings)
    try:
        repos = list_active_repos_for_vendor(session, vendor_slug)
    finally:
        session.close()
    dispatched = 0
    for repo in repos:
        try:
            app = _get_celery_app()
            if app is not None:
                app.send_task(
                    "argus.scan_and_fix", args=[repo.id], kwargs={"merge": True}
                )
            else:
                raise RuntimeError("celery unavailable")
        except Exception:  # noqa: BLE001
            threading.Thread(
                target=scan_and_fix,
                args=(repo.id,),
                kwargs={"merge": True},
                daemon=True,
            ).start()
        dispatched += 1
    return {"dispatched": dispatched, "vendor": vendor_slug, "repos": len(repos)}


def sync_installation_repos(install_id: int, installation_token: str) -> dict:
    """Query GitHub API for repos in this installation, upsert into DB."""
    settings = get_settings()
    client = GitHubClient(token=installation_token)
    try:
        repos = client.list_installation_repositories(installation_token)
    except (GitHubApiError, OSError) as exc:
        return {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}
    session = open_session(settings)
    try:
        for repo_data in repos:
            owner = repo_data["owner"]["login"]
            name = repo_data["name"]
            default_branch = repo_data.get("default_branch")
            upsert_repository(session, owner, name, default_branch, vendor_slug="github")
        session.commit()
    finally:
        session.close()
    return {"synced": len(repos), "install_id": install_id}


def sync_all_installation_repos() -> dict:
    """Iterate all active installations, sync repos for each."""
    settings = get_settings()
    if not settings.database_url:
        return {"error": "DATABASE_URL not set"}
    session = open_session(settings)
    try:
        installations = list_installations(session)
    finally:
        session.close()
    results = {}
    for inst in installations:
        if not inst.is_active:
            continue
        results[str(inst.install_id)] = {
            "install_id": inst.install_id,
            "owner": inst.owner,
            "status": "skipped_no_token",
        }
    return {"installations": len(results), "results": results}


def merge_pr(owner: str, repo: str, pr_number: int) -> dict:
    settings = get_settings()
    client = GitHubClient(token=settings.github_token)
    try:
        result = client.merge_pull_request(owner, repo, pr_number)
        return {"owner": owner, "repo": repo, "pr_number": pr_number, "merged": True, "result": result}
    except (GitHubApiError, OSError) as exc:
        return {
            "owner": owner,
            "repo": repo,
            "pr_number": pr_number,
            "merged": False,
            "error": f"{type(exc).__name__}: {str(exc)[:200]}",
        }


def poll_all_vendors() -> dict:
    settings = get_settings()
    summary: dict[str, dict] = {}
    for vendor in list_vendors(settings):
        if not vendor.enabled:
            continue
        try:
            result = run_detection(vendor.slug)
            summary[vendor.slug] = result
            if result.get("breaking_count", 0) > 0:
                try:
                    app = _get_celery_app()
                    if app is not None:
                        app.send_task(
                            "argus.dispatch_scan_for_vendor",
                            args=[vendor.slug, result["breaking_count"]],
                        )
                    else:
                        raise RuntimeError("celery unavailable")
                except Exception:  # noqa: BLE001
                    threading.Thread(
                        target=dispatch_scan_for_vendor,
                        args=(vendor.slug, result["breaking_count"]),
                        daemon=True,
                    ).start()
        except (GitHubApiError, OSError, ValueError) as exc:
            summary[vendor.slug] = {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}
    return summary
