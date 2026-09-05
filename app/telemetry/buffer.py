from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any

from app.core.config import Settings
from app.telemetry.models import TelemetryEvent


class TelemetryBuffer:
    """Ring buffer that batches telemetry events and flushes to DB."""

    def __init__(self, settings: Settings):
        self._buffer: deque[TelemetryEvent] = deque(maxlen=settings.telemetry_buffer_size)
        self._last_flush = time.monotonic()
        self._flush_interval = settings.telemetry_flush_interval_seconds
        self._settings = settings
        self._lock = threading.Lock()
        self._flush_callback = None

    def set_flush_callback(self, callback) -> None:
        self._flush_callback = callback

    def add(self, event: TelemetryEvent) -> None:
        with self._lock:
            self._buffer.append(event)
        if self._should_flush():
            self.flush()

    def flush(self) -> int:
        with self._lock:
            if not self._buffer:
                return 0
            events = list(self._buffer)
            self._buffer.clear()
            self._last_flush = time.monotonic()

        if self._flush_callback:
            try:
                self._flush_callback(events)
            except Exception:
                pass

        return len(events)

    def _should_flush(self) -> bool:
        return (time.monotonic() - self._last_flush) >= self._flush_interval

    @property
    def pending_count(self) -> int:
        return len(self._buffer)
