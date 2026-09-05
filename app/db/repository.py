from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.engine import init_db, session_factory
from app.db.models import (
    AppInstallation,
    ChangelogEntry,
    DriftAlert,
    Investigation,
    Repository,
    TelemetryEvent,
    Vendor,
)
from app.registry.vendors import Vendor as VendorSpec
from app.search.embeddings import build_embedder, cosine_similarity

DEFAULT_ENGINE = None

_SCHEMA_READY: set[str] = set()


def open_session(settings: Settings) -> Session:
    if DEFAULT_ENGINE is None:
        if not settings.database_url:
            raise RuntimeError("DATABASE_URL is not set; configure it in .env")
        from app.db.engine import get_engine

        engine = get_engine(settings.database_url)
        if settings.database_url not in _SCHEMA_READY:
            init_db(engine)
            _SCHEMA_READY.add(settings.database_url)
        return session_factory(engine)()
    return session_factory(DEFAULT_ENGINE)()


def set_default_engine(engine) -> None:
    global DEFAULT_ENGINE
    DEFAULT_ENGINE = engine
    from app.db.engine import init_db

    init_db(engine)


def upsert_vendor(session: Session, spec: VendorSpec) -> Vendor:
    row = session.get(Vendor, spec.slug)
    if row is None:
        row = Vendor(slug=spec.slug, name=spec.name)
        session.add(row)
    row.name = spec.name
    row.enabled = spec.enabled
    return row


def upsert_repository(
    session: Session,
    owner: str,
    name: str,
    default_branch: str | None = None,
    git_provider: str = "github",
    vendor_slug: str = "github",
    tenant_id: str | None = None,
) -> Repository:
    row = session.execute(
        select(Repository).where(
            Repository.owner == owner, Repository.name == name
        )
    ).scalar_one_or_none()
    if row is None:
        row = Repository(
            owner=owner, name=name, default_branch=default_branch,
            git_provider=git_provider, vendor_slug=vendor_slug, tenant_id=tenant_id,
        )
        session.add(row)
    else:
        row.default_branch = default_branch or row.default_branch
        row.git_provider = git_provider or row.git_provider
        row.vendor_slug = vendor_slug or row.vendor_slug
        if tenant_id is not None:
            row.tenant_id = tenant_id
    return row


def list_active_repositories(session: Session, tenant_id: str | None = None) -> list[Repository]:
    stmt = select(Repository).where(Repository.is_active.is_(True))
    if tenant_id is not None:
        stmt = stmt.where(Repository.tenant_id == tenant_id)
    return list(session.execute(stmt).scalars())


def list_active_repos_for_vendor(
    session: Session, vendor_slug: str, tenant_id: str | None = None
) -> list[Repository]:
    stmt = select(Repository).where(
        Repository.is_active.is_(True),
        Repository.vendor_slug == vendor_slug,
    )
    if tenant_id is not None:
        stmt = stmt.where(Repository.tenant_id == tenant_id)
    return list(session.execute(stmt).scalars())


def touch_repository(session: Session, repo: Repository) -> None:
    repo.last_run_at = datetime.now(UTC)


def upsert_app_installation(
    session: Session, install_id: int, owner: str, is_active: bool = True,
    tenant_id: str | None = None,
) -> AppInstallation:
    row = session.execute(
        select(AppInstallation).where(AppInstallation.install_id == install_id)
    ).scalar_one_or_none()
    if row is None:
        row = AppInstallation(
            install_id=install_id, owner=owner, is_active=is_active,
            tenant_id=tenant_id,
        )
        session.add(row)
    else:
        row.owner = owner
        row.is_active = is_active
        if tenant_id is not None:
            row.tenant_id = tenant_id
    return row


def list_installations(session: Session, tenant_id: str | None = None) -> list[AppInstallation]:
    stmt = select(AppInstallation)
    if tenant_id is not None:
        stmt = stmt.where(
            (AppInstallation.tenant_id == tenant_id)
            | (AppInstallation.tenant_id.is_(None))
        )
    return list(session.execute(stmt).scalars())


def record_telemetry_event(
    session: Session,
    vendor_slug: str,
    endpoint: str,
    method: str,
    path: str,
    status_code: int,
    drift_detected: bool = False,
    drift_details: dict | None = None,
    response_schema_hash: str | None = None,
    request_body_hash: str | None = None,
    tenant_id: str | None = None,
) -> TelemetryEvent:
    row = TelemetryEvent(
        vendor_slug=vendor_slug,
        tenant_id=tenant_id,
        endpoint=endpoint,
        method=method,
        path=path,
        status_code=status_code,
        drift_detected=drift_detected,
        drift_details=drift_details,
        response_schema_hash=response_schema_hash,
        request_body_hash=request_body_hash,
        captured_at=datetime.now(UTC),
    )
    session.add(row)
    return row


def create_drift_alert(
    session: Session,
    vendor_slug: str,
    alert_type: str,
    severity: str,
    details: dict,
    endpoint: str | None = None,
    tenant_id: str | None = None,
) -> DriftAlert:
    row = DriftAlert(
        vendor_slug=vendor_slug,
        tenant_id=tenant_id,
        alert_type=alert_type,
        severity=severity,
        endpoint=endpoint,
        details=details,
    )
    session.add(row)
    session.flush()
    return row


def resolve_drift_alert(session: Session, alert_id: int) -> None:
    row = session.get(DriftAlert, alert_id)
    if row is not None:
        row.resolved = True


def create_investigation(
    session: Session,
    drift_alert_id: int,
    vendor_slug: str,
    changelog_snippets: list | None = None,
    doc_references: list | None = None,
    context_summary: str | None = None,
    confidence_score: float | None = None,
) -> Investigation:
    row = Investigation(
        drift_alert_id=drift_alert_id,
        vendor_slug=vendor_slug,
        changelog_snippets=changelog_snippets,
        doc_references=doc_references,
        context_summary=context_summary,
        confidence_score=confidence_score,
    )
    session.add(row)
    session.flush()
    return row


def record_changelog_entries(
    session: Session,
    vendor_slug: str,
    entries: list[dict],
    embedder=None,
) -> list[ChangelogEntry]:
    texts = [
        f"{e.get('title', '')} | {e.get('content', '')[:200]}"
        for e in entries
    ]
    vectors = embedder(texts) if embedder is not None and texts else None
    rows: list[ChangelogEntry] = []
    for index, e in enumerate(entries):
        rows.append(
            ChangelogEntry(
                vendor_slug=vendor_slug,
                source_url=e.get("source_url", ""),
                title=e.get("title", ""),
                content=e.get("content", ""),
                published_at=e.get("published_at"),
                embedding=vectors[index] if vectors is not None else None,
            )
        )
    session.add_all(rows)
    return rows


def search_changelog(
    session: Session,
    query: str,
    vendor_slug: str | None = None,
    limit: int = 10,
    embedder=None,
    tenant_id: str | None = None,
) -> list[tuple[ChangelogEntry, float]]:
    statement = select(ChangelogEntry)
    if vendor_slug:
        statement = statement.where(ChangelogEntry.vendor_slug == vendor_slug)
    rows = list(session.execute(statement).scalars())
    if not rows:
        return []

    qvec = None
    if embedder is not None:
        try:
            qvec = embedder([query])[0]
        except (TypeError, IndexError, KeyError):
            qvec = None
    if qvec:
        scored = [
            (row, cosine_similarity(qvec, row.embedding)) for row in rows if row.embedding
        ]
        if scored:
            return sorted(scored, key=lambda item: item[1], reverse=True)[:limit]

    terms = [t for t in query.lower().split() if t]
    scored = []
    for row in rows:
        haystack = " ".join([row.title, row.content[:500]]).lower()
        score = sum(1 for t in terms if t in haystack)
        if score > 0:
            scored.append((row, float(score)))
    return sorted(scored, key=lambda item: item[1], reverse=True)[:limit]


def list_open_drift_alerts(
    session: Session,
    vendor_slug: str | None = None,
    tenant_id: str | None = None,
) -> list[DriftAlert]:
    stmt = select(DriftAlert).where(DriftAlert.resolved.is_(False))
    if vendor_slug:
        stmt = stmt.where(DriftAlert.vendor_slug == vendor_slug)
    if tenant_id is not None:
        stmt = stmt.where(DriftAlert.tenant_id == tenant_id)
    stmt = stmt.order_by(DriftAlert.created_at.desc())
    return list(session.execute(stmt).scalars())
