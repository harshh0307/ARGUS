from app.core.config import Settings
from app.detection.detect import run_detection
from app.ingestion.fetcher import FetchResult


class StubFetcher:
    def __init__(self, by_url):
        self.by_url = by_url

    def fetch(self, url, etag=None):
        return FetchResult(content=self.by_url[url])


def test_run_detection_end_to_end(tmp_path):
    old = {"paths": {"/gone": {"get": {"responses": {"200": {}}}}}}
    new = {"paths": {}}
    fetcher = StubFetcher({"https://old": old, "https://new": new})
    settings = Settings(
        github_old_spec_url="https://old",
        github_spec_url="https://new",
        snapshot_dir=str(tmp_path),
    )

    result = run_detection(settings, fetcher=fetcher)

    assert result["breaking_count"] == 1
    assert result["additive_count"] == 0
    assert result["old_digest"] != result["new_digest"]
