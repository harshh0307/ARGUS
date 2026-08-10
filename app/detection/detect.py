from __future__ import annotations

from app.core.config import Settings
from app.detection.diff import diff_specs
from app.detection.models import ADDITIVE, BREAKING
from app.ingestion.fetcher import SpecFetcher, SpecFetchError
from app.ingestion.ingest import ingest
from app.ingestion.snapshot_store import SnapshotStore
from app.registry.vendors import Vendor, get_vendor


def run_detection(
    settings: Settings,
    vendor_slug: str = "github",
    fetcher: SpecFetcher | None = None,
    store: SnapshotStore | None = None,
) -> dict:
    fetcher = fetcher or SpecFetcher(settings)
    store = store or SnapshotStore(settings.snapshot_dir)
    vendor: Vendor = get_vendor(settings, vendor_slug)

    if vendor.old_spec_url:
        old_result = fetcher.fetch(vendor.old_spec_url)
        if old_result is None:
            raise SpecFetchError(f"could not fetch old spec: {vendor.old_spec_url}")
        old_digest = store.pin(vendor_slug, "old", old_result.content)
        old = store.pinned(vendor_slug, "old")
    else:
        baseline = store.latest(vendor_slug)
        if baseline is None:
            ingest(settings, vendor_slug, fetcher, store)
            return {
                "vendor": vendor_slug,
                "old_digest": None,
                "new_digest": None,
                "changes": [],
                "breaking_count": 0,
                "additive_count": 0,
                "baselined": True,
            }
        old_digest = baseline["digest"]
        old = {"digest": old_digest, "content": store.load(vendor_slug, old_digest)}

    ingest(settings, vendor_slug, fetcher, store)

    latest = store.latest(vendor_slug)
    if latest is None:
        raise SpecFetchError("current spec snapshot is missing")
    current = store.load(vendor_slug, latest["digest"])

    changes = diff_specs(old["content"], current)
    return {
        "vendor": vendor_slug,
        "old_digest": old_digest,
        "new_digest": latest["digest"],
        "changes": changes,
        "breaking_count": sum(1 for c in changes if c.severity == BREAKING),
        "additive_count": sum(1 for c in changes if c.severity == ADDITIVE),
    }