from __future__ import annotations

from app.core.config import Settings
from app.ingestion.fetcher import SpecFetcher
from app.ingestion.snapshot_store import SnapshotStore
from app.registry.vendors import Vendor, get_vendor


def ingest(
    settings: Settings,
    vendor_slug: str = "github",
    fetcher: SpecFetcher | None = None,
    store: SnapshotStore | None = None,
) -> dict:
    fetcher = fetcher or SpecFetcher(settings)
    store = store or SnapshotStore(settings.snapshot_dir)
    vendor: Vendor = get_vendor(settings, vendor_slug)

    result = fetcher.fetch(vendor.spec_url)
    if result is None:
        return {"status": "unchanged", "vendor": vendor_slug, "digest": None}
    digest = store.save(vendor_slug, result.content, etag=result.etag, spec_format=result.spec_format)
    return {"status": "stored", "vendor": vendor_slug, "digest": digest}
