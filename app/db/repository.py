from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.engine import init_db, session_factory
from app.db.models import (
    AppInstallation,
    ChangelogEntry,
    DetectionRun,
    Repository,
    SpecSnapshot,
    Vendor,
)
from app.registry.vendors import Vendor as VendorSpec
from app.search.embeddings import build_embedder, cosine_similarity, embed_text

DEFAULT_ENGINE = None


def open_session(settings: Settings) -> Session:
    if DEFAULT_ENGINE is None:
        engine = None
        if not settings.database_url:
            raise RuntimeError("DATABASE_URL is not set; configure it in .env")
        from app.db.engine import get_engine

        engine = get_engine(settings.database_url)
        init_db(engine)
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
    row.spec_url = spec.spec_url
    row.old_spec_url = spec.old_spec_url
    row.poll_interval_seconds = spec.poll_interval_seconds
    row.enabled = spec.enabled
    return row


def record_snapshot(
    session: Session, vendor_slug: str, digest: str, etag: str | None = None
) -> SpecSnapshot:
    existing = session.execute(
        select(SpecSnapshot).where(
            SpecSnapshot.vendor_slug == vendor_slug, SpecSnapshot.digest == digest
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    row = SpecSnapshot(vendor_slug=vendor_slug, digest=digest, etag=etag)
    session.add(row)
    return row


def record_detection_run(
    session: Session, vendor_slug: str, result: dict
) -> DetectionRun:
    row = DetectionRun(
        vendor_slug=vendor_slug,
        old_digest=result.get("old_digest"),
        new_digest=result.get("new_digest"),
        breaking_count=result.get("breaking_count", 0),
        additive_count=result.get("additive_count", 0),
        changes=[
            {
                "kind": c.kind,
                "severity": c.severity,
                "path": c.path,
                "method": c.method,
                "detail": c.detail,
            }
            for c in result.get("changes", [])
        ],
    )
    session.add(row)
    return row


def persist_detection(settings: Settings, vendor_slug: str, result: dict, spec: VendorSpec) -> DetectionRun | None:
    if not settings.database_url:
        return None
    session = open_session(settings)
    try:
        upsert_vendor(session, spec)
        if result.get("old_digest"):
            record_snapshot(session, vendor_slug, result["old_digest"])
        if result.get("new_digest"):
            record_snapshot(session, vendor_slug, result["new_digest"])
        run = record_detection_run(session, vendor_slug, result)
        session.flush()
        embedder = build_embedder(settings)
        record_changelog_entries(
            session,
            vendor_slug,
            run,
            run.changes,
            embedder=embedder,
        )
        session.commit()
        return run
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def upsert_repository(
    session: Session,
    owner: str,
    name: str,
    default_branch: str | None = None,
    vendor_slug: str = "github",
) -> Repository:
    row = session.execute(
        select(Repository).where(
            Repository.owner == owner, Repository.name == name
        )
    ).scalar_one_or_none()
    if row is None:
        row = Repository(
            owner=owner, name=name, default_branch=default_branch, vendor_slug=vendor_slug
        )
        session.add(row)
    else:
        row.default_branch = default_branch or row.default_branch
        row.vendor_slug = vendor_slug or row.vendor_slug
    return row


def list_active_repositories(session: Session) -> list[Repository]:
    return list(
        session.execute(
            select(Repository).where(Repository.is_active.is_(True))
        ).scalars()
    )


def touch_repository(session: Session, repo: Repository) -> None:
    repo.last_run_at = datetime.now(UTC)


def upsert_app_installation(
    session: Session, install_id: int, owner: str, is_active: bool = True
) -> AppInstallation:
    row = session.execute(
        select(AppInstallation).where(AppInstallation.install_id == install_id)
    ).scalar_one_or_none()
    if row is None:
        row = AppInstallation(install_id=install_id, owner=owner, is_active=is_active)
        session.add(row)
    else:
        row.owner = owner
        row.is_active = is_active
    return row


def list_installations(session: Session) -> list[AppInstallation]:
    return list(session.execute(select(AppInstallation)).scalars())


def record_changelog_entries(
    session: Session,
    vendor_slug: str,
    run: DetectionRun,
    changes: list,
    embedder=None,
) -> list[ChangelogEntry]:
    texts = [
        embed_text(c.get("kind", "change"), c.get("path", ""), c.get("method", ""), c.get("detail"))
        for c in changes
    ]
    vectors = embedder(texts) if embedder is not None and texts else None
    rows: list[ChangelogEntry] = []
    for index, c in enumerate(changes):
        rows.append(
            ChangelogEntry(
                vendor_slug=vendor_slug,
                run_id=run.id,
                kind=c.get("kind", "change"),
                path=c.get("path", ""),
                method=c.get("method", ""),
                detail=c.get("detail"),
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
) -> list[tuple[ChangelogEntry, float]]:
    statement = select(ChangelogEntry)
    if vendor_slug:
        statement = statement.where(ChangelogEntry.vendor_slug == vendor_slug)
    rows = list(session.execute(statement).scalars())
    if not rows:
        return []

    qvec = embedder([query])[0] if embedder is not None else None
    if qvec:
        scored = [
            (row, cosine_similarity(qvec, row.embedding)) for row in rows if row.embedding
        ]
        if scored:
            return sorted(scored, key=lambda item: item[1], reverse=True)[:limit]

    terms = [t for t in query.lower().split() if t]
    scored = []
    for row in rows:
        haystack = " ".join([row.kind, row.path, row.method, row.detail or ""]).lower()
        score = sum(1 for t in terms if t in haystack)
        if score > 0:
            scored.append((row, float(score)))
    return sorted(scored, key=lambda item: item[1], reverse=True)[:limit]