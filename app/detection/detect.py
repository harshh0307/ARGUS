from __future__ import annotations

from app.core.config import Settings
from app.detection.diff import diff_specs
from app.detection.models import ADDITIVE, BREAKING
from app.ingestion.fetcher import SpecFetcher, SpecFetchError
from app.ingestion.ingest import ingest
from app.ingestion.snapshot_store import SnapshotStore


def run_detection(
    settings: Settings,
    fetcher: SpecFetcher | None = None,
    store: SnapshotStore | None = None,
) -> dict:
    fetcher = fetcher or SpecFetcher(settings)
    store = store or SnapshotStore(settings.snapshot_dir)

    old_result = fetcher.fetch(settings.github_old_spec_url)
    if old_result is None:
        raise SpecFetchError(f"could not fetch old spec: {settings.github_old_spec_url}")
    old_digest = store.pin("github", "old", old_result.content)

    ingest(settings, fetcher, store)

    latest = store.latest("github")
    if latest is None:
        raise SpecFetchError("current spec snapshot is missing")
    current = store.load("github", latest["digest"])
    old = store.pinned("github", "old")

    changes = diff_specs(old["content"], current)
    return {
        "old_digest": old_digest,
        "new_digest": latest["digest"],
        "changes": changes,
        "breaking_count": sum(1 for c in changes if c.severity == BREAKING),
        "additive_count": sum(1 for c in changes if c.severity == ADDITIVE),
    }
