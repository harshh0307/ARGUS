from __future__ import annotations

from app.core.config import Settings
from app.ingestion.fetcher import SpecFetcher
from app.ingestion.snapshot_store import SnapshotStore


def ingest(
    settings: Settings,
    fetcher: SpecFetcher | None = None,
    store: SnapshotStore | None = None,
) -> dict:
    fetcher = fetcher or SpecFetcher(settings)
    store = store or SnapshotStore(settings.snapshot_dir)

    result = fetcher.fetch(settings.github_spec_url)
    if result is None:
        return {"status": "unchanged", "digest": None}
    digest = store.save("github", result.content, etag=result.etag)
    return {"status": "stored", "vendor": "github", "digest": digest}
