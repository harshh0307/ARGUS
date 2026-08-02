from __future__ import annotations

import time

import httpx

from app.core.config import Settings


class SpecFetchError(Exception):
    pass


class FetchResult:
    def __init__(self, content: dict, etag: str | None = None):
        self.content = content
        self.etag = etag


class SpecFetcher:
    def __init__(self, settings: Settings, client: httpx.Client | None = None):
        self.settings = settings
        self._client = client or httpx.Client(
            headers={"User-Agent": "argus/0.1 (api-change-agent)"},
            timeout=settings.http_timeout_seconds,
        )

    def fetch(self, url: str, etag: str | None = None) -> FetchResult | None:
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
                return FetchResult(content=response.json(), etag=response.headers.get("ETag"))
            if attempt == self.settings.http_max_retries - 1:
                raise SpecFetchError(
                    f"unexpected status {response.status_code} for {url}"
                )
        return None
