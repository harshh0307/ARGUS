from __future__ import annotations

import threading
import time
from urllib.parse import urlparse

import httpx
import yaml

from app.core.config import Settings


class SpecFetchError(Exception):
    pass


class FetchResult:
    def __init__(self, content: dict, etag: str | None = None, spec_format: str = "json"):
        self.content = content
        self.etag = etag
        self.spec_format = spec_format


class SpecCache:
    """In-memory cache for fetched specs with TTL-based expiration."""

    def __init__(self, ttl_seconds: int = 300):
        self._cache: dict[str, tuple[float, FetchResult]] = {}
        self._lock = threading.Lock()
        self._ttl = ttl_seconds

    def get(self, url: str) -> FetchResult | None:
        with self._lock:
            entry = self._cache.get(url)
            if entry is None:
                return None
            timestamp, result = entry
            if time.time() - timestamp > self._ttl:
                del self._cache[url]
                return None
            return result

    def put(self, url: str, result: FetchResult) -> None:
        with self._lock:
            self._cache[url] = (time.time(), result)

    def invalidate(self, url: str) -> None:
        with self._lock:
            self._cache.pop(url, None)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._cache)


class SpecFetcher:
    def __init__(self, settings: Settings, client: httpx.Client | None = None):
        self.settings = settings
        self._client = client or httpx.Client(
            headers={"User-Agent": "argus/0.1 (api-change-agent)"},
            timeout=settings.http_timeout_seconds,
        )
        self._cache = SpecCache(ttl_seconds=getattr(settings, "spec_cache_ttl_seconds", 300))

    @property
    def cache(self) -> SpecCache:
        return self._cache

    def fetch(self, url: str, etag: str | None = None) -> FetchResult | None:
        # Check cache first
        cached = self._cache.get(url)
        if cached is not None:
            return cached

        headers = {}
        if etag:
            headers["If-None-Match"] = etag
        for attempt in range(self.settings.http_max_retries):
            try:
                response = self._client.get(url, headers=headers)
            except httpx.TransportError as exc:
                if attempt == self.settings.http_max_retries - 1:
                    raise SpecFetchError(
                        f"network failure fetching {url} after {attempt + 1} attempts"
                    ) from exc
                time.sleep(self.settings.http_backoff_base_seconds * (2**attempt))
                continue
            if response.status_code == 304:
                return None
            if response.status_code == 200:
                content_type = response.headers.get("Content-Type", "")
                spec_format = _detect_format(url, content_type)
                content = _parse_response(response.text, spec_format)
                result = FetchResult(content=content, etag=response.headers.get("ETag"), spec_format=spec_format)
                self._cache.put(url, result)
                return result
            if attempt == self.settings.http_max_retries - 1:
                raise SpecFetchError(
                    f"unexpected status {response.status_code} for {url}"
                )
        return None


def _detect_format(url: str, content_type: str) -> str:
    ct = content_type.lower()
    if "yaml" in ct or "x-yaml" in ct:
        return "yaml"
    parsed = urlparse(url)
    path = parsed.path.lower()
    if path.endswith((".yaml", ".yml")):
        return "yaml"
    return "json"


def _parse_response(text: str, spec_format: str) -> dict:
    if spec_format == "yaml":
        return yaml.safe_load(text)
    import json
    return json.loads(text)
