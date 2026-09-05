from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import httpx

from app.core.config import Settings
from app.telemetry.buffer import TelemetryBuffer
from app.telemetry.drift_detector import DriftDetector
from app.telemetry.models import TelemetryEvent

_endpoint_segment_re = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
    r"|\d{10,}"
    r"|[0-9a-f]{40}"
)


class ArgusClient:
    """Instrumented HTTP client that wraps httpx with drift detection."""

    def __init__(self, vendor_slug: str, settings: Settings):
        self.vendor_slug = vendor_slug
        self.settings = settings
        self._client = httpx.Client(timeout=settings.http_timeout_seconds)
        self._detector = DriftDetector(vendor_slug, settings)
        self._buffer = TelemetryBuffer(settings)

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        response = self._client.request(method, url, **kwargs)

        endpoint = self._extract_endpoint(url, method)

        body = None
        try:
            body = response.json()
        except Exception:  # noqa: BLE001
            body = None

        drift = self._detector.check(endpoint, response.status_code, body)

        event = TelemetryEvent(
            vendor_slug=self.vendor_slug,
            endpoint=endpoint,
            method=method,
            path=url,
            status_code=response.status_code,
            response_schema_hash=self._hash_response(body),
            drift_detected=drift is not None,
            drift_details=drift.details if drift else None,
            captured_at=datetime.now(UTC),
        )
        self._buffer.add(event)

        return response

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("POST", url, **kwargs)

    def put(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("PUT", url, **kwargs)

    def delete(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("DELETE", url, **kwargs)

    def close(self) -> None:
        self._client.close()
        self._buffer.flush()

    def _extract_endpoint(self, url: str, method: str) -> str:
        try:
            parsed = urlparse(url)
            path = parsed.path
        except Exception:  # noqa: BLE001
            path = url

        segments = path.strip("/").split("/")
        normalized = []
        for seg in segments:
            if _endpoint_segment_re.match(seg) or re.match(r"^\d+$", seg):
                normalized.append("{id}")
            else:
                normalized.append(seg)

        return f"{method.upper()} /{'/'.join(normalized)}"

    def _hash_response(self, body: Any) -> str | None:
        if body is None:
            return None
        try:
            schema = self._detector._extract_schema(body)
            raw = json.dumps(schema, sort_keys=True)
            return hashlib.sha256(raw.encode()).hexdigest()[:16]
        except Exception:  # noqa: BLE001
            return None
