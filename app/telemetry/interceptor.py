from __future__ import annotations

import fnmatch
import re
from typing import Any


class RequestInterceptor:
    """Middleware that intercepts outbound HTTP requests for telemetry."""

    def __init__(self, patterns: list[str] | None = None):
        self._patterns = patterns or []
        self._enabled = True

    def should_intercept(self, url: str) -> bool:
        if not self._enabled:
            return False
        if not self._patterns:
            return True
        return any(fnmatch.fnmatch(url, p) for p in self._patterns)

    def on_request(self, method: str, url: str, headers: dict, body: Any = None) -> None:
        pass

    def on_response(self, method: str, url: str, status_code: int, body: Any = None) -> None:
        pass

    def disable(self) -> None:
        self._enabled = False

    def enable(self) -> None:
        self._enabled = True
