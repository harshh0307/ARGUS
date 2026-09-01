from __future__ import annotations

import hashlib
import hmac
import json
import threading
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import (
    ChangelogHitOut,
    DetectIn,
    DetectionRunOut,
    DetectOut,
    InstallationOut,
    MergeIn,
    MergeOut,
    PipelineIn,
    PipelineOut,
    PollOut,
    RepositoryCreated,
    RepositoryIn,
    RepositoryOut,
    RerunIn,
    RerunOut,
    VendorOut,
    WebhookOut,
)
from app.core.config import Settings, get_settings
from app.db.models import DetectionRun, Repository
from app.db.repository import open_session, upsert_repository
from app.github.client import GitHubClient
from app.registry.vendors import get_vendor, list_vendors
from app.workers.celery_app import app as celery_app

_templates_dir = Path(__file__).parent / "templates"
_templates = Jinja2Templates(directory=str(_templates_dir))


def _db_session(settings: Settings) -> Session:
    if not settings.database_url:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "DATABASE_URL is not set; the API read endpoints need a database",
        )
    return open_session(settings)


def _from_request(request: Request) -> Settings:
    return request.app.state.settings


SettingsDep = Annotated[Settings, Depends(_from_request)]


def _list_vendor_rows(settings: Settings) -> list[VendorOut]:
    return [
        VendorOut(
            slug=v.slug,
            name=v.name,
            spec_url=v.spec_url,
            old_spec_url=v.old_spec_url,
            poll_interval_seconds=v.poll_interval_seconds,
            enabled=v.enabled,
        )
        for v in list_vendors(settings)
    ]


def _verify_signature(secret: str, signature: str | None, body: bytes) -> bool:
    if not signature or not signature.startswith("sha256="):
        return False
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, f"sha256={digest}")


def _dispatch_scan_and_fix(repository_id: int, merge: bool = False) -> bool:
    """Enqueue the celery task; if the broker is unreachable, fall back to an
    inline run in a daemon thread so self-hosted setups without Redis still work."""
    try:
        celery_app.send_task(
            "argus.scan_and_fix", args=[repository_id], kwargs={"merge": merge}
        )
        return True
    except Exception:  # noqa: BLE001 - broker unreachable; run inline
        from app.workers import tasks

        threading.Thread(
            target=tasks.scan_and_fix, args=(repository_id,), kwargs={"merge": merge},
            daemon=True,
        ).start()
        return False


def _repo_from_push(payload: dict) -> tuple[str, str]:
    return payload["repository"]["owner"]["login"], payload["repository"]["name"]


def _handle_push(payload: dict, settings: Settings) -> WebhookOut:
    owner, name = _repo_from_push(payload)
    session = _db_session(settings)
    try:
        repo = session.execute(
            select(Repository).where(Repository.owner == owner, Repository.name == name)
        ).scalar_one_or_none()
    finally:
        session.close()
    if repo is None or not repo.is_active:
        return WebhookOut(ok=True, event="push", dispatched=False, reason="repository not registered")
    dispatched = _dispatch_scan_and_fix(repo.id)
    return WebhookOut(ok=True, event="push", dispatched=dispatched)


def _handle_installation(payload: dict, settings: Settings) -> WebhookOut:
    from app.db.repository import upsert_app_installation

    action = payload.get("action", "")
    install_id = payload["installation"]["id"]
    owner = payload["installation"]["account"]["login"]
    if action in ("deleted", "unsuspended"):
        is_active = False
    elif action in ("created", "suspend"):
        is_active = True
    else:
        return WebhookOut(ok=True, event="installation", reason=f"ignored action {action!r}")
    session = _db_session(settings)
    try:
        upsert_app_installation(session, install_id, owner, is_active=is_active)
        session.commit()
    finally:
        session.close()
    return WebhookOut(
        ok=True,
        event="installation",
        dispatched=False,
        reason=f"installation {action} -> owner {owner} active={is_active}",
    )


def _handle_repository_dispatch(payload: dict, settings: Settings) -> WebhookOut:
    owner, name = _repo_from_push(payload)
    session = _db_session(settings)
    try:
        repo = session.execute(
            select(Repository).where(Repository.owner == owner, Repository.name == name)
        ).scalar_one_or_none()
    finally:
        session.close()
    if repo is None or not repo.is_active:
        return WebhookOut(ok=True, event="repository_dispatch", dispatched=False, reason="repository not registered")
    dispatched = _dispatch_scan_and_fix(repo.id)
    return WebhookOut(ok=True, event="repository_dispatch", dispatched=dispatched)


_WEBHOOK_HANDLERS = {
    "push": _handle_push,
    "installation": _handle_installation,
    "repository_dispatch": _handle_repository_dispatch,
}


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(title="Argus API", version="0.1.0")
    app.state.settings = settings or get_settings()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "https://web-seven-cyan-48.vercel.app",
            "https://*.vercel.app",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health(request: Request) -> dict:
        return {"status": "ok", "database": bool(app.state.settings.database_url)}

    @app.get("/api/v1/vendors", response_model=list[VendorOut])
    def vendors(settings: SettingsDep) -> list[VendorOut]:
        return _list_vendor_rows(settings)

    @app.get("/api/v1/vendors/{slug}", response_model=VendorOut)
    def vendor(slug: str, settings: SettingsDep) -> VendorOut:
        try:
            spec = get_vendor(settings, slug)
        except ValueError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
        return VendorOut(
            slug=spec.slug,
            name=spec.name,
            spec_url=spec.spec_url,
            old_spec_url=spec.old_spec_url,
            poll_interval_seconds=spec.poll_interval_seconds,
            enabled=spec.enabled,
        )

    @app.get("/api/v1/detection-runs", response_model=list[DetectionRunOut])
    def detection_runs(
        settings: SettingsDep, limit: int = Query(default=50, ge=1, le=500)
    ) -> list[DetectionRunOut]:
        session = _db_session(settings)
        try:
            rows = session.execute(
                select(DetectionRun).order_by(DetectionRun.id.desc()).limit(limit)
            ).scalars().all()
            return [
                DetectionRunOut(
                    id=r.id,
                    vendor_slug=r.vendor_slug,
                    old_digest=r.old_digest,
                    new_digest=r.new_digest,
                    breaking_count=r.breaking_count,
                    additive_count=r.additive_count,
                    changes=r.changes or [],
                    created_at=r.created_at,
                )
                for r in rows
            ]
        finally:
            session.close()

    @app.get("/api/v1/detection-runs/{run_id}", response_model=DetectionRunOut)
    def detection_run(run_id: int, settings: SettingsDep) -> DetectionRunOut:
        session = _db_session(settings)
        try:
            row = session.get(DetectionRun, run_id)
            if row is None:
                raise HTTPException(
                    status.HTTP_404_NOT_FOUND, f"detection run {run_id} not found"
                )
            return DetectionRunOut(
                id=row.id,
                vendor_slug=row.vendor_slug,
                old_digest=row.old_digest,
                new_digest=row.new_digest,
                breaking_count=row.breaking_count,
                additive_count=row.additive_count,
                changes=row.changes or [],
                created_at=row.created_at,
            )
        finally:
            session.close()

    @app.get("/api/v1/repositories", response_model=list[RepositoryOut])
    def repositories(settings: SettingsDep) -> list[RepositoryOut]:
        session = _db_session(settings)
        try:
            rows = session.execute(
                select(Repository).order_by(Repository.id)
            ).scalars().all()
            return [
                RepositoryOut(
                    id=r.id,
                    owner=r.owner,
                    name=r.name,
                    vendor_slug=r.vendor_slug,
                    default_branch=r.default_branch,
                    is_active=r.is_active,
                    last_run_at=r.last_run_at,
                    created_at=r.created_at,
                )
                for r in rows
            ]
        finally:
            session.close()

    @app.post("/api/v1/repositories", response_model=RepositoryCreated, status_code=201)
    def register_repository(
        payload: RepositoryIn, settings: SettingsDep
    ) -> RepositoryCreated:
        session = _db_session(settings)
        try:
            row = upsert_repository(
                session,
                payload.owner,
                payload.name,
                payload.default_branch,
                payload.vendor_slug,
            )
            session.commit()
            return RepositoryCreated(id=row.id)
        finally:
            session.close()

    @app.get("/api/v1/installations", response_model=list[InstallationOut])
    def installations(settings: SettingsDep) -> list[InstallationOut]:
        from app.db.repository import list_installations

        session = _db_session(settings)
        try:
            rows = list_installations(session)
            return [
                InstallationOut(
                    id=r.id,
                    install_id=r.install_id,
                    owner=r.owner,
                    is_active=r.is_active,
                    created_at=r.created_at,
                )
                for r in rows
            ]
        finally:
            session.close()

    @app.get("/api/v1/search/changelog", response_model=list[ChangelogHitOut])
    def search_changelog(
        settings: SettingsDep,
        q: str = Query("", description="search terms"),
        vendor: str | None = Query(None),
        limit: int = Query(10, ge=1, le=100),
    ) -> list[ChangelogHitOut]:
        from app.db.repository import search_changelog as search_rows
        from app.search.embeddings import build_embedder

        session = _db_session(settings)
        try:
            hits = search_rows(
                session,
                q,
                vendor_slug=vendor,
                limit=limit,
                embedder=build_embedder(settings),
            )
            return [
                ChangelogHitOut(
                    id=row.id,
                    vendor_slug=row.vendor_slug,
                    kind=row.kind,
                    path=row.path,
                    method=row.method,
                    detail=row.detail,
                    score=score,
                    created_at=row.created_at,
                )
                for row, score in hits
            ]
        finally:
            session.close()

    @app.post("/api/v1/webhook", response_model=WebhookOut)
    async def webhook(request: Request, settings: SettingsDep) -> WebhookOut:
        if not settings.webhook_secret:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "WEBHOOK_SECRET is not configured",
            )
        event = request.headers.get("X-GitHub-Event", "")
        body = await request.body()
        if not _verify_signature(settings.webhook_secret, request.headers.get("X-Hub-Signature-256"), body):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid webhook signature")
        try:
            payload = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid JSON payload") from exc

        handler = _WEBHOOK_HANDLERS.get(event)
        if handler is None:
            return WebhookOut(ok=True, event=event, dispatched=False, reason="ignored event")
        try:
            return handler(payload, settings)
        except KeyError as exc:
            return WebhookOut(ok=True, event=event, dispatched=False, reason=f"malformed payload: missing {exc}")

    # ── Control endpoints ────────────────────────────────────────────

    def _dispatch_task(task_name: str, args: list | None = None, kwargs: dict | None = None) -> tuple[bool, str | None]:
        try:
            result = celery_app.send_task(task_name, args=args or [], kwargs=kwargs or {})
            return True, result.id
        except Exception:  # noqa: BLE001

            from app.workers import tasks as worker_tasks
            func = getattr(worker_tasks, task_name.replace("argus.", "").replace(".", "_"), None)
            if func is None:
                return False, None
            threading.Thread(target=func, args=args or [], kwargs=kwargs or {}, daemon=True).start()
            return True, None

    @app.post("/api/v1/poll", response_model=PollOut)
    def trigger_poll(settings: SettingsDep) -> PollOut:
        dispatched, task_id = _dispatch_task("argus.poll_all_vendors")
        return PollOut(dispatched=dispatched, task_id=task_id)

    @app.post("/api/v1/detect", response_model=DetectOut)
    def trigger_detect(payload: DetectIn, settings: SettingsDep) -> DetectOut:
        dispatched, task_id = _dispatch_task(
            "argus.run_detection", args=[payload.vendor_slug]
        )
        return DetectOut(dispatched=dispatched, vendor_slug=payload.vendor_slug, task_id=task_id)

    @app.post("/api/v1/pipeline", response_model=PipelineOut)
    def trigger_pipeline(payload: PipelineIn, settings: SettingsDep) -> PipelineOut:
        dispatched, task_id = _dispatch_task(
            "argus.scan_and_fix",
            args=[payload.repository_id],
            kwargs={"merge": payload.merge},
        )
        return PipelineOut(
            dispatched=dispatched, repository_id=payload.repository_id, task_id=task_id
        )

    @app.post("/api/v1/fix/rerun", response_model=RerunOut)
    def trigger_rerun(payload: RerunIn, settings: SettingsDep) -> RerunOut:
        dispatched, task_id = _dispatch_task(
            "argus.scan_and_fix",
            args=[payload.repository_id],
            kwargs={"merge": False},
        )
        return RerunOut(
            dispatched=dispatched, repository_id=payload.repository_id, task_id=task_id
        )

    @app.post("/api/v1/pr/merge", response_model=MergeOut)
    def trigger_merge(payload: MergeIn, settings: SettingsDep) -> MergeOut:
        def _do_merge():
            client = GitHubClient(token=settings.github_token)
            client.merge_pull_request(payload.owner, payload.repo, payload.pr_number)

        try:
            celery_app.send_task(
                "argus.merge_pr",
                args=[payload.owner, payload.repo, payload.pr_number],
            )
            return MergeOut(
                dispatched=True,
                owner=payload.owner,
                repo=payload.repo,
                pr_number=payload.pr_number,
                task_id=None,
            )
        except Exception:  # noqa: BLE001
            threading.Thread(target=_do_merge, daemon=True).start()
            return MergeOut(
                dispatched=True,
                owner=payload.owner,
                repo=payload.repo,
                pr_number=payload.pr_number,
                task_id=None,
            )

    # ── Dashboard routes ─────────────────────────────────────────────
    from app.api.dashboard import router as dashboard_router

    app.include_router(dashboard_router)

    @app.get("/dashboard", response_class=HTMLResponse)
    def dashboard_index_html(request: Request) -> HTMLResponse:
        from app.api.dashboard import dashboard_index
        data = dashboard_index(request, app.state.settings)
        return _templates.TemplateResponse("index.html", {"request": request, **data})

    @app.get("/dashboard/vendors", response_class=HTMLResponse)
    def dashboard_vendors_html(request: Request) -> HTMLResponse:
        from app.api.dashboard import dashboard_vendors
        data = dashboard_vendors(request, app.state.settings)
        return _templates.TemplateResponse("vendors.html", {"request": request, **data})

    @app.get("/dashboard/activity", response_class=HTMLResponse)
    def dashboard_activity_html(request: Request, days: int = 30) -> HTMLResponse:
        from app.api.dashboard import dashboard_activity
        data = dashboard_activity(request, app.state.settings, days=days)
        return _templates.TemplateResponse("activity.html", {"request": request, **data})

    @app.get("/dashboard/repositories", response_class=HTMLResponse)
    def dashboard_repositories_html(request: Request) -> HTMLResponse:
        from app.api.dashboard import dashboard_repositories
        data = dashboard_repositories(request, app.state.settings)
        return _templates.TemplateResponse("repositories.html", {"request": request, **data})

    return app


app = create_app()