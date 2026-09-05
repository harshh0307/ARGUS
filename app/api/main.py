from __future__ import annotations

import hashlib
import hmac
import json
import threading
from datetime import timedelta
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import (
    ActivityEventOut,
    ApiKeyCreatedOut,
    ApiKeyOut,
    ChangelogHitOut,
    DetectIn,
    DetectOut,
    DriftAlertOut,
    InstallationOut,
    LoginIn,
    MergeIn,
    MergeOut,
    PipelineIn,
    PipelineOut,
    PipelineRunOut,
    PollOut,
    RefreshIn,
    RegisterIn,
    RegisterOut,
    RepositoryCreated,
    RepositoryIn,
    RepositoryOut,
    RerunIn,
    RerunOut,
    TokenOut,
    VendorCreated,
    VendorIn,
    VendorOut,
    WebhookOut,
)
from app.auth.api_keys import generate_api_key
from app.auth.deps import AdminUser, CurrentUser
from app.auth.jwt import create_access_token, create_refresh_token, decode_token
from app.auth.password import hash_password, verify_password
from app.core.config import Settings, get_settings
from app.db.models import ApiKey, DriftAlert, PipelineRun, Repository, User, Vendor
from app.db.repository import open_session, upsert_repository
from app.github.client import GitHubClient
from app.registry.vendors import get_vendor, list_vendors


def _celery_app():
    from app.workers.celery_app import app
    return app

_templates_dir = Path(__file__).parent / "templates"
_templates = Jinja2Templates(directory=str(_templates_dir))


def _rate_limit_handler(request: Request, exc) -> HTMLResponse:
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=429,
        content={"error": "rate limit exceeded", "detail": str(exc)},
    )


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
            enabled=v.enabled,
            base_api_url=v.base_api_url,
            changelog_urls=v.changelog_urls,
            docs_url=v.docs_url,
            fix_guidance=v.fix_guidance,
        )
        for v in list_vendors(settings)
    ]


def _vendor_out_from_db(row: Vendor) -> VendorOut:
    return VendorOut(
        slug=row.slug,
        name=row.name,
        enabled=row.enabled,
    )


def _verify_signature(secret: str, signature: str | None, body: bytes) -> bool:
    if not signature or not signature.startswith("sha256="):
        return False
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, f"sha256={digest}")


def _dispatch_scan_and_fix(repository_id: int, merge: bool = False) -> bool:
    """Enqueue the celery task; if the broker is unreachable, fall back to an
    inline run in a daemon thread so self-hosted setups without Redis still work."""
    try:
        _celery_app().send_task(
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


def _handle_pull_request(payload: dict, settings: Settings) -> WebhookOut:
    """Handle pull_request webhook: trigger scan on PR opened/synchronize."""
    action = payload.get("action", "")
    if action not in ("opened", "synchronize", "reopened"):
        return WebhookOut(ok=True, event="pull_request", dispatched=False, reason=f"ignored action {action!r}")

    owner, name = _repo_from_push(payload)
    session = _db_session(settings)
    try:
        repo = session.execute(
            select(Repository).where(Repository.owner == owner, Repository.name == name)
        ).scalar_one_or_none()
    finally:
        session.close()
    if repo is None or not repo.is_active:
        return WebhookOut(ok=True, event="pull_request", dispatched=False, reason="repository not registered")
    dispatched = _dispatch_scan_and_fix(repo.id)
    pr_number = payload.get("pull_request", {}).get("number")
    return WebhookOut(ok=True, event="pull_request", dispatched=dispatched, reason=f"PR #{pr_number} {action}")


def _handle_check_run(payload: dict, settings: Settings) -> WebhookOut:
    """Handle check_run webhook: log CI check results."""
    action = payload.get("action", "")
    if action not in ("completed", "created"):
        return WebhookOut(ok=True, event="check_run", dispatched=False, reason=f"ignored action {action!r}")

    check_run = payload.get("check_run", {})
    conclusion = check_run.get("conclusion", "")
    name = check_run.get("name", "")
    return WebhookOut(ok=True, event="check_run", dispatched=False, reason=f"check {name!r} concluded {conclusion!r}")


_WEBHOOK_HANDLERS = {
    "push": _handle_push,
    "installation": _handle_installation,
    "repository_dispatch": _handle_repository_dispatch,
    "pull_request": _handle_pull_request,
    "check_run": _handle_check_run,
}


def create_app(settings: Settings | None = None) -> FastAPI:
    from slowapi import Limiter
    from slowapi.errors import RateLimitExceeded
    from slowapi.util import get_remote_address

    app = FastAPI(title="Argus API", version="0.1.0")
    app.state.settings = settings or get_settings()

    limiter = Limiter(
        key_func=get_remote_address,
        default_limits=[app.state.settings.rate_limit_default],
        storage_uri="memory://",
    )
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)

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

    @app.get("/metrics")
    def metrics_endpoint() -> dict:
        from app.metrics import metrics
        return metrics.export()

    # ── Auth endpoints ────────────────────────────────────────────────

    @app.post("/api/v1/auth/register", response_model=RegisterOut, status_code=201)
    @limiter.limit(app.state.settings.rate_limit_auth)
    def auth_register(request: Request, payload: RegisterIn, settings: SettingsDep) -> RegisterOut:
        session = _db_session(settings)
        try:
            existing = session.execute(
                select(User).where(User.email == payload.email)
            ).scalar_one_or_none()
            if existing:
                raise HTTPException(status.HTTP_409_CONFLICT, "email already registered")

            tenant_id = payload.tenant_id or payload.email.split("@")[0]
            user = User(
                email=payload.email,
                hashed_password=hash_password(payload.password),
                tenant_id=tenant_id,
            )
            session.add(user)
            session.commit()
            session.refresh(user)
            return RegisterOut(id=user.id, email=user.email, tenant_id=user.tenant_id)
        finally:
            session.close()

    @app.post("/api/v1/auth/login", response_model=TokenOut)
    @limiter.limit(app.state.settings.rate_limit_auth)
    def auth_login(request: Request, payload: LoginIn, settings: SettingsDep) -> TokenOut:
        session = _db_session(settings)
        try:
            user = session.execute(
                select(User).where(User.email == payload.email)
            ).scalar_one_or_none()
            if not user or not verify_password(payload.password, user.hashed_password):
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")
            if not user.is_active:
                raise HTTPException(status.HTTP_403_FORBIDDEN, "account disabled")

            access = create_access_token(
                {"sub": str(user.id)},
                settings.auth_secret_key,
                timedelta(minutes=settings.access_token_expire_minutes),
                settings.auth_algorithm,
            )
            refresh = create_refresh_token(
                {"sub": str(user.id)},
                settings.auth_secret_key,
                timedelta(days=settings.refresh_token_expire_days),
                settings.auth_algorithm,
            )
            return TokenOut(access_token=access, refresh_token=refresh)
        finally:
            session.close()

    @app.post("/api/v1/auth/refresh", response_model=TokenOut)
    def auth_refresh(payload: RefreshIn, settings: SettingsDep) -> TokenOut:
        payload_data = decode_token(
            payload.refresh_token, settings.auth_secret_key, settings.auth_algorithm
        )
        if not payload_data or payload_data.get("type") != "refresh":
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid refresh token")

        user_id = payload_data.get("sub")
        session = _db_session(settings)
        try:
            user = session.get(User, int(user_id))
            if not user or not user.is_active:
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user not found or disabled")

            access = create_access_token(
                {"sub": str(user.id)},
                settings.auth_secret_key,
                timedelta(minutes=settings.access_token_expire_minutes),
                settings.auth_algorithm,
            )
            refresh = create_refresh_token(
                {"sub": str(user.id)},
                settings.auth_secret_key,
                timedelta(days=settings.refresh_token_expire_days),
                settings.auth_algorithm,
            )
            return TokenOut(access_token=access, refresh_token=refresh)
        finally:
            session.close()

    @app.get("/api/v1/auth/me")
    def auth_me(current_user: CurrentUser) -> dict:
        return {
            "id": current_user.id,
            "email": current_user.email,
            "tenant_id": current_user.tenant_id,
            "is_admin": current_user.is_admin,
        }

    # ── API Key management ───────────────────────────────────────────

    @app.post("/api/v1/auth/api-keys", response_model=ApiKeyCreatedOut, status_code=201)
    def create_api_key(
        name: str, settings: SettingsDep, current_user: CurrentUser
    ) -> ApiKeyCreatedOut:
        raw_key, key_hash, prefix = generate_api_key()
        session = _db_session(settings)
        try:
            api_key = ApiKey(
                user_id=current_user.id,
                key_hash=key_hash,
                name=name,
                prefix=prefix,
            )
            session.add(api_key)
            session.commit()
            session.refresh(api_key)
            return ApiKeyCreatedOut(
                id=api_key.id,
                name=api_key.name,
                key=raw_key,
                prefix=prefix,
                created_at=api_key.created_at,
            )
        finally:
            session.close()

    @app.get("/api/v1/auth/api-keys", response_model=list[ApiKeyOut])
    def list_api_keys(settings: SettingsDep, current_user: CurrentUser) -> list[ApiKeyOut]:
        session = _db_session(settings)
        try:
            rows = session.execute(
                select(ApiKey).where(ApiKey.user_id == current_user.id)
            ).scalars().all()
            return [
                ApiKeyOut(
                    id=r.id,
                    name=r.name,
                    prefix=r.prefix,
                    is_active=r.is_active,
                    created_at=r.created_at,
                    last_used_at=r.last_used_at,
                )
                for r in rows
            ]
        finally:
            session.close()

    @app.delete("/api/v1/auth/api-keys/{key_id}", status_code=204)
    def revoke_api_key(
        key_id: int, settings: SettingsDep, current_user: CurrentUser
    ) -> None:
        session = _db_session(settings)
        try:
            row = session.get(ApiKey, key_id)
            if row is None or row.user_id != current_user.id:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "API key not found")
            row.is_active = False
            session.commit()
        finally:
            session.close()

    @app.get("/api/v1/vendors", response_model=list[VendorOut])
    def vendors(settings: SettingsDep, current_user: CurrentUser) -> list[VendorOut]:
        return _list_vendor_rows(settings)

    @app.get("/api/v1/vendors/{slug}", response_model=VendorOut)
    def vendor(slug: str, settings: SettingsDep, current_user: CurrentUser) -> VendorOut:
        try:
            spec = get_vendor(settings, slug)
        except ValueError:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"vendor {slug!r} not found")
        return VendorOut(
            slug=spec.slug,
            name=spec.name,
            enabled=spec.enabled,
            base_api_url=spec.base_api_url,
            changelog_urls=spec.changelog_urls,
            docs_url=spec.docs_url,
            fix_guidance=spec.fix_guidance,
        )

    @app.post("/api/v1/vendors", response_model=VendorCreated, status_code=201)
    def create_vendor(payload: VendorIn, settings: SettingsDep, current_user: CurrentUser) -> VendorCreated:
        slug = payload.slug or payload.name.lower().replace(" ", "_").replace("-", "_")
        session = _db_session(settings)
        try:
            existing = session.get(Vendor, slug)
            if existing is not None:
                raise HTTPException(
                    status.HTTP_409_CONFLICT, f"vendor {slug!r} already exists"
                )
            row = Vendor(
                slug=slug,
                name=payload.name,
                enabled=payload.enabled,
                tenant_id=current_user.tenant_id,
            )
            session.add(row)
            session.commit()
            return VendorCreated(slug=slug)
        finally:
            session.close()

    @app.put("/api/v1/vendors/{slug}", response_model=VendorOut)
    def update_vendor(slug: str, payload: VendorIn, settings: SettingsDep, current_user: CurrentUser) -> VendorOut:
        session = _db_session(settings)
        try:
            row = session.get(Vendor, slug)
            if row is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, f"vendor {slug!r} not found")
            if not current_user.is_admin and row.tenant_id is not None and row.tenant_id != current_user.tenant_id:
                raise HTTPException(status.HTTP_404_NOT_FOUND, f"vendor {slug!r} not found")
            row.name = payload.name
            row.enabled = payload.enabled
            session.commit()
            return _vendor_out_from_db(row)
        finally:
            session.close()

    @app.delete("/api/v1/vendors/{slug}", status_code=204)
    def delete_vendor(slug: str, settings: SettingsDep, current_user: CurrentUser) -> None:
        session = _db_session(settings)
        try:
            row = session.get(Vendor, slug)
            if row is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, f"vendor {slug!r} not found")
            if not current_user.is_admin and row.tenant_id is not None and row.tenant_id != current_user.tenant_id:
                raise HTTPException(status.HTTP_404_NOT_FOUND, f"vendor {slug!r} not found")
            session.delete(row)
            session.commit()
        finally:
            session.close()

    @app.get("/api/v1/detection-runs", response_model=list[DriftAlertOut])
    def detection_runs(
        settings: SettingsDep, current_user: CurrentUser, limit: int = Query(default=50, ge=1, le=500)
    ) -> list[DriftAlertOut]:
        session = _db_session(settings)
        try:
            stmt = select(DriftAlert).order_by(DriftAlert.id.desc()).limit(limit)
            if not current_user.is_admin:
                stmt = stmt.where(
                    (DriftAlert.tenant_id == current_user.tenant_id)
                    | (DriftAlert.tenant_id.is_(None))
                )
            rows = session.execute(stmt).scalars().all()
            return [
                DriftAlertOut(
                    id=r.id,
                    vendor_slug=r.vendor_slug,
                    alert_type=r.alert_type,
                    severity=r.severity,
                    endpoint=r.endpoint,
                    details=r.details or {},
                    resolved=r.resolved,
                    created_at=r.created_at,
                )
                for r in rows
            ]
        finally:
            session.close()

    @app.get("/api/v1/detection-runs/{run_id}", response_model=DriftAlertOut)
    def detection_run(run_id: int, settings: SettingsDep, current_user: CurrentUser) -> DriftAlertOut:
        session = _db_session(settings)
        try:
            row = session.get(DriftAlert, run_id)
            if row is None:
                raise HTTPException(
                    status.HTTP_404_NOT_FOUND, f"detection run {run_id} not found"
                )
            if not current_user.is_admin and row.tenant_id is not None and row.tenant_id != current_user.tenant_id:
                raise HTTPException(status.HTTP_404_NOT_FOUND, f"detection run {run_id} not found")
            return DriftAlertOut(
                id=row.id,
                vendor_slug=row.vendor_slug,
                alert_type=row.alert_type,
                severity=row.severity,
                endpoint=row.endpoint,
                details=row.details or {},
                resolved=row.resolved,
                created_at=row.created_at,
            )
        finally:
            session.close()

    @app.get("/api/v1/repositories", response_model=list[RepositoryOut])
    def repositories(settings: SettingsDep, current_user: CurrentUser) -> list[RepositoryOut]:
        session = _db_session(settings)
        try:
            if not current_user.is_admin:
                rows = session.execute(
                    select(Repository).where(Repository.tenant_id == current_user.tenant_id)
                ).scalars().all()
            else:
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
        payload: RepositoryIn, settings: SettingsDep, current_user: CurrentUser
    ) -> RepositoryCreated:
        session = _db_session(settings)
        try:
            row = upsert_repository(
                session,
                payload.owner,
                payload.name,
                payload.default_branch,
                vendor_slug=payload.vendor_slug,
            )
            row.tenant_id = current_user.tenant_id
            session.commit()
            _dispatch_task(
                "argus.scan_and_fix",
                args=[row.id],
                kwargs={"merge": True},
            )
            return RepositoryCreated(id=row.id)
        finally:
            session.close()

    @app.get("/api/v1/installations", response_model=list[InstallationOut])
    def installations(settings: SettingsDep, current_user: CurrentUser) -> list[InstallationOut]:
        from app.db.repository import list_installations

        session = _db_session(settings)
        try:
            tenant_id = None if current_user.is_admin else current_user.tenant_id
            rows = list_installations(session, tenant_id=tenant_id)
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
        current_user: CurrentUser,
        q: str = Query("", description="search terms"),
        vendor: str | None = Query(None),
        limit: int = Query(10, ge=1, le=100),
    ) -> list[ChangelogHitOut]:
        from app.db.repository import search_changelog as search_rows
        from app.search.embeddings import build_embedder

        session = _db_session(settings)
        try:
            tenant_id = None if current_user.is_admin else current_user.tenant_id
            hits = search_rows(
                session,
                q,
                vendor_slug=vendor,
                limit=limit,
                embedder=build_embedder(settings),
                tenant_id=tenant_id,
            )
            return [
                ChangelogHitOut(
                    id=row.id,
                    vendor_slug=row.vendor_slug,
                    kind=row.title,
                    path=row.source_url,
                    method="",
                    detail=row.content[:200] if row.content else "",
                    score=score,
                    created_at=row.fetched_at,
                )
                for row, score in hits
            ]
        finally:
            session.close()

    @app.get("/api/v1/pipeline-runs", response_model=list[PipelineRunOut])
    def pipeline_runs(
        settings: SettingsDep, current_user: CurrentUser, limit: int = Query(default=20, ge=1, le=100)
    ) -> list[PipelineRunOut]:
        session = _db_session(settings)
        try:
            stmt = (
                select(PipelineRun)
                .join(Repository, PipelineRun.repository_id == Repository.id)
                .order_by(PipelineRun.id.desc())
                .limit(limit)
            )
            if not current_user.is_admin:
                stmt = stmt.where(
                    (Repository.tenant_id == current_user.tenant_id)
                    | (Repository.tenant_id.is_(None))
                )
            rows = session.execute(stmt).scalars().all()
            return [
                PipelineRunOut(
                    id=r.id,
                    repository_id=r.repository_id,
                    status=r.status,
                    current_step=r.current_step,
                    task_id=r.task_id,
                    started_at=r.started_at,
                    completed_at=r.completed_at,
                    pr_number=r.pr_number,
                    pr_url=r.pr_url,
                    error_message=r.error_message,
                    created_at=r.created_at,
                )
                for r in rows
            ]
        finally:
            session.close()

    @app.get("/api/v1/pipeline-runs/{run_id}", response_model=PipelineRunOut)
    def pipeline_run(run_id: int, settings: SettingsDep, current_user: CurrentUser) -> PipelineRunOut:
        session = _db_session(settings)
        try:
            row = session.get(PipelineRun, run_id)
            if row is None:
                raise HTTPException(
                    status.HTTP_404_NOT_FOUND, f"pipeline run {run_id} not found"
                )
            if not current_user.is_admin:
                repo = session.get(Repository, row.repository_id)
                if repo is None or (repo.tenant_id is not None and repo.tenant_id != current_user.tenant_id):
                    raise HTTPException(status.HTTP_404_NOT_FOUND, f"pipeline run {run_id} not found")
            return PipelineRunOut(
                id=row.id,
                repository_id=row.repository_id,
                status=row.status,
                current_step=row.current_step,
                task_id=row.task_id,
                started_at=row.started_at,
                completed_at=row.completed_at,
                pr_number=row.pr_number,
                pr_url=row.pr_url,
                error_message=row.error_message,
                created_at=row.created_at,
            )
        finally:
            session.close()

    @app.get("/api/v1/activity", response_model=list[ActivityEventOut])
    def activity(
        settings: SettingsDep, current_user: CurrentUser, limit: int = Query(default=30, ge=1, le=100)
    ) -> list[ActivityEventOut]:
        """Combined timeline of detection runs and pipeline runs."""
        session = _db_session(settings)
        try:
            events: list[ActivityEventOut] = []
            det_stmt = select(DriftAlert).order_by(DriftAlert.id.desc()).limit(limit)
            if not current_user.is_admin:
                det_stmt = det_stmt.where(
                    (DriftAlert.tenant_id == current_user.tenant_id)
                    | (DriftAlert.tenant_id.is_(None))
                )
            detections = session.execute(det_stmt).scalars().all()
            for r in detections:
                title = f"Drift alert: {r.alert_type} ({r.severity}) in {r.vendor_slug}"
                events.append(ActivityEventOut(
                    kind="detection",
                    timestamp=r.created_at,
                    title=title,
                    detail=f"Alert #{r.id} — {r.endpoint or 'N/A'}",
                    status=r.severity,
                ))
            pipe_stmt = (
                select(PipelineRun)
                .join(Repository, PipelineRun.repository_id == Repository.id)
                .order_by(PipelineRun.id.desc())
                .limit(limit)
            )
            if not current_user.is_admin:
                pipe_stmt = pipe_stmt.where(
                    (Repository.tenant_id == current_user.tenant_id)
                    | (Repository.tenant_id.is_(None))
                )
            pipelines = session.execute(pipe_stmt).scalars().all()
            for r in pipelines:
                repo = session.get(Repository, r.repository_id)
                repo_name = f"{repo.owner}/{repo.name}" if repo else f"repo #{r.repository_id}"
                title = f"Pipeline for {repo_name}"
                detail_parts = []
                if r.pr_number:
                    detail_parts.append(f"PR #{r.pr_number}")
                if r.error_message:
                    detail_parts.append(r.error_message[:100])
                events.append(ActivityEventOut(
                    kind="pipeline",
                    timestamp=r.created_at,
                    title=title,
                    detail=" — ".join(detail_parts) if detail_parts else None,
                    status=r.status,
                ))
            events.sort(key=lambda e: e.timestamp, reverse=True)
            return events[:limit]
        finally:
            session.close()

    @app.post("/api/v1/webhook", response_model=WebhookOut)
    @limiter.limit(app.state.settings.rate_limit_webhook)
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
            result = _celery_app().send_task(task_name, args=args or [], kwargs=kwargs or {})
            return True, result.id
        except Exception:  # noqa: BLE001

            from app.workers import tasks as worker_tasks
            func = getattr(worker_tasks, task_name.replace("argus.", "").replace(".", "_"), None)
            if func is None:
                return False, None
            threading.Thread(target=func, args=args or [], kwargs=kwargs or {}, daemon=True).start()
            return True, None

    @app.post("/api/v1/poll", response_model=PollOut)
    def trigger_poll(settings: SettingsDep, current_user: AdminUser) -> PollOut:
        dispatched, task_id = _dispatch_task("argus.poll_all_vendors")
        return PollOut(dispatched=dispatched, task_id=task_id)

    @app.post("/api/v1/detect", response_model=DetectOut)
    def trigger_detect(payload: DetectIn, settings: SettingsDep, current_user: AdminUser) -> DetectOut:
        dispatched, task_id = _dispatch_task(
            "argus.run_detection", args=[payload.vendor_slug]
        )
        return DetectOut(dispatched=dispatched, vendor_slug=payload.vendor_slug, task_id=task_id)

    @app.post("/api/v1/pipeline", response_model=PipelineOut)
    def trigger_pipeline(payload: PipelineIn, settings: SettingsDep, current_user: CurrentUser) -> PipelineOut:
        session = _db_session(settings)
        try:
            repo = session.get(Repository, payload.repository_id)
            if repo is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, f"repository {payload.repository_id} not found")
            if not current_user.is_admin and repo.tenant_id is not None and repo.tenant_id != current_user.tenant_id:
                raise HTTPException(status.HTTP_404_NOT_FOUND, f"repository {payload.repository_id} not found")
        finally:
            session.close()
        dispatched, task_id = _dispatch_task(
            "argus.scan_and_fix",
            args=[payload.repository_id],
            kwargs={"merge": payload.merge},
        )
        return PipelineOut(
            dispatched=dispatched, repository_id=payload.repository_id, task_id=task_id
        )

    @app.post("/api/v1/fix/rerun", response_model=RerunOut)
    def trigger_rerun(payload: RerunIn, settings: SettingsDep, current_user: CurrentUser) -> RerunOut:
        session = _db_session(settings)
        try:
            repo = session.get(Repository, payload.repository_id)
            if repo is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, f"repository {payload.repository_id} not found")
            if not current_user.is_admin and repo.tenant_id is not None and repo.tenant_id != current_user.tenant_id:
                raise HTTPException(status.HTTP_404_NOT_FOUND, f"repository {payload.repository_id} not found")
        finally:
            session.close()
        dispatched, task_id = _dispatch_task(
            "argus.scan_and_fix",
            args=[payload.repository_id],
            kwargs={"merge": False},
        )
        return RerunOut(
            dispatched=dispatched, repository_id=payload.repository_id, task_id=task_id
        )

    @app.post("/api/v1/pr/merge", response_model=MergeOut)
    def trigger_merge(payload: MergeIn, settings: SettingsDep, current_user: CurrentUser) -> MergeOut:
        session = _db_session(settings)
        try:
            repo = session.execute(
                select(Repository).where(
                    Repository.owner == payload.owner, Repository.name == payload.repo
                )
            ).scalar_one_or_none()
            if repo is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, f"repository {payload.owner}/{payload.repo} not found")
            if not current_user.is_admin and repo.tenant_id is not None and repo.tenant_id != current_user.tenant_id:
                raise HTTPException(status.HTTP_404_NOT_FOUND, f"repository {payload.owner}/{payload.repo} not found")
        finally:
            session.close()

        def _do_merge():
            client = GitHubClient(token=settings.github_token)
            client.merge_pull_request(payload.owner, payload.repo, payload.pr_number)

        try:
            _celery_app().send_task(
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