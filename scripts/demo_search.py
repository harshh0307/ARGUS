"""Seed the changelog with sample vendor changes so the search endpoint can be
tried without running a full detection against live spec URLs.

Usage:
    python scripts/demo_search.py [--db sqlite:///data/argus.db]
    uvicorn app.api.main:app
    curl "http://127.0.0.1:8000/api/v1/search/changelog?q=delete%20repository"
"""

from __future__ import annotations

import argparse
import sys

from app.core.config import Settings
from app.db.engine import get_engine, init_db, session_factory
from app.db.models import Vendor
from app.db.repository import persist_detection
from app.detection.models import Change
from app.registry.vendors import Vendor as VendorSpec

SAMPLE_CHANGES = [
    {
        "kind": "endpoint_removed",
        "severity": "breaking",
        "path": "/repos/{owner}/{repo}",
        "method": "delete",
        "detail": "Delete a repository was removed",
    },
    {
        "kind": "endpoint_added",
        "severity": "additive",
        "path": "/repos/{owner}/{repo}/transfer",
        "method": "post",
        "detail": "Transfer a repository to another owner",
    },
    {
        "kind": "parameter_added_required",
        "severity": "breaking",
        "path": "/issues/{issue_number}",
        "method": "patch",
        "detail": "Required new parameter 'milestone'",
    },
    {
        "kind": "schema_added",
        "severity": "additive",
        "path": "/pulls",
        "method": "get",
        "detail": "New response schema field 'auto_merge'",
    },
    {
        "kind": "endpoint_added",
        "severity": "additive",
        "path": "/actions/cache/usage",
        "method": "get",
        "detail": "List GitHub Actions cache usage",
    },
    {
        "kind": "response_code_removed",
        "severity": "breaking",
        "path": "/search/code",
        "method": "get",
        "detail": "Response code 200 removed, only 202 remains",
    },
    {
        "kind": "endpoint_added",
        "severity": "additive",
        "path": "/codespaces/{codespace_name}/export",
        "method": "post",
        "detail": "Export a codespace",
    },
    {
        "kind": "endpoint_added",
        "severity": "additive",
        "path": "/orgs/{org}/dependabot/secrets",
        "method": "get",
        "detail": "List organization dependabot secrets",
    },
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed demo changelog data")
    parser.add_argument("--db", default=None, help="DATABASE_URL override")
    args = parser.parse_args()

    settings = Settings(database_url=args.db) if args.db else Settings()
    if not settings.database_url:
        print("error: DATABASE_URL is not set (pass --db sqlite:///data/argus.db)")
        return 1

    engine = get_engine(settings.database_url)
    init_db(engine)
    session = session_factory(engine)()
    try:
        vendor = VendorSpec(
            slug="github",
            name="GitHub",
            spec_url="https://example.com/demo-spec.json",
        )
        session.merge(
            Vendor(
                slug=vendor.slug,
                name=vendor.name,
                spec_url=vendor.spec_url,
            )
        )
        session.commit()
    finally:
        session.close()

    result = {
        "old_digest": "demo-old",
        "new_digest": "demo-new",
        "breaking_count": sum(1 for c in SAMPLE_CHANGES if c["severity"] == "breaking"),
        "additive_count": sum(1 for c in SAMPLE_CHANGES if c["severity"] == "additive"),
        "changes": [Change(**c) for c in SAMPLE_CHANGES],
    }
    run = persist_detection(settings, "github", result, vendor)
    print(f"seeded {len(SAMPLE_CHANGES)} changes as detection run #{run.id}")
    print("start the API with:  uvicorn app.api.main:app")
    print('try:  curl "http://127.0.0.1:8000/api/v1/search/changelog?q=transfer%20repository"')
    return 0


if __name__ == "__main__":
    sys.exit(main())