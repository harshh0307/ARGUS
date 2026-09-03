"""Prometheus-style metrics for observability.

Uses a simple in-memory counter/histogram registry. For production,
swap this with prometheus_client or opentelemetry.
"""

from __future__ import annotations

import threading
from collections import defaultdict


class Counter:
    """Thread-safe counter metric."""

    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self._value: float = 0
        self._lock = threading.Lock()
        self._labels: dict[str, float] = defaultdict(float)

    def inc(self, value: float = 1.0, **labels: str) -> None:
        key = self._label_key(labels)
        with self._lock:
            self._labels[key] += value

    def _label_key(self, labels: dict[str, str]) -> str:
        return "|".join(f"{k}={v}" for k, v in sorted(labels.items()))

    def value(self, **labels: str) -> float:
        key = self._label_key(labels)
        with self._lock:
            return self._labels.get(key, 0.0)

    def total(self) -> float:
        with self._lock:
            return sum(self._labels.values())


class Histogram:
    """Thread-safe histogram metric for tracking distributions."""

    def __init__(self, name: str, description: str = "", buckets: list[float] | None = None):
        self.name = name
        self.description = description
        self._buckets = buckets or [0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0]
        self._counts: dict[str, list[int]] = defaultdict(lambda: [0] * (len(self._buckets) + 1))
        self._sums: dict[str, float] = defaultdict(float)
        self._lock = threading.Lock()

    def observe(self, value: float, **labels: str) -> None:
        key = "|".join(f"{k}={v}" for k, v in sorted(labels.items()))
        with self._lock:
            self._sums[key] += value
            for i, bound in enumerate(self._buckets):
                if value <= bound:
                    self._counts[key][i] += 1
                    return
            self._counts[key][-1] += 1  # +Inf bucket

    def count(self, **labels: str) -> int:
        key = "|".join(f"{k}={v}" for k, v in sorted(labels.items()))
        with self._lock:
            return sum(self._counts.get(key, []))

    def mean(self, **labels: str) -> float:
        key = "|".join(f"{k}={v}" for k, v in sorted(labels.items()))
        with self._lock:
            c = sum(self._counts.get(key, []))
            if c == 0:
                return 0.0
            return self._sums.get(key, 0.0) / c


class Gauge:
    """Thread-safe gauge metric."""

    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self._value: float = 0
        self._lock = threading.Lock()

    def set(self, value: float) -> None:
        with self._lock:
            self._value = value

    def inc(self, value: float = 1.0) -> None:
        with self._lock:
            self._value += value

    def dec(self, value: float = 1.0) -> None:
        with self._lock:
            self._value -= value

    def value(self) -> float:
        with self._lock:
            return self._value


# ── Registry ────────────────────────────────────────────────────────────────


class MetricsRegistry:
    """Central registry for all metrics."""

    def __init__(self):
        self._counters: dict[str, Counter] = {}
        self._histograms: dict[str, Histogram] = {}
        self._gauges: dict[str, Gauge] = {}
        self._lock = threading.Lock()

    def counter(self, name: str, description: str = "") -> Counter:
        with self._lock:
            if name not in self._counters:
                self._counters[name] = Counter(name, description)
            return self._counters[name]

    def histogram(self, name: str, description: str = "", buckets: list[float] | None = None) -> Histogram:
        with self._lock:
            if name not in self._histograms:
                self._histograms[name] = Histogram(name, description, buckets)
            return self._histograms[name]

    def gauge(self, name: str, description: str = "") -> Gauge:
        with self._lock:
            if name not in self._gauges:
                self._gauges[name] = Gauge(name, description)
            return self._gauges[name]

    def export(self) -> dict:
        """Export all metrics as a dict (for /metrics endpoint)."""
        with self._lock:
            result = {}
            for name, c in self._counters.items():
                result[f"counter_{name}"] = c.total()
            for name, h in self._histograms.items():
                result[f"histogram_{name}_count"] = h.count()
                result[f"histogram_{name}_mean"] = h.mean()
            for name, g in self._gauges.items():
                result[f"gauge_{name}"] = g.value()
            return result


# ── Global instance ─────────────────────────────────────────────────────────


metrics = MetricsRegistry()

# ── Pre-defined metrics ─────────────────────────────────────────────────────

detection_runs_total = metrics.counter("detection_runs_total", "Total detection runs")
fix_attempts_total = metrics.counter("fix_attempts_total", "Total fix attempts")
fix_successes_total = metrics.counter("fix_successes_total", "Total successful fixes")
fix_failures_total = metrics.counter("fix_failures_total", "Total failed fixes")
webhook_events_total = metrics.counter("webhook_events_total", "Total webhook events received")
pr_created_total = metrics.counter("pr_created_total", "Total PRs created")
pr_merged_total = metrics.counter("pr_merged_total", "Total PRs merged")
spec_fetch_duration = metrics.histogram("spec_fetch_duration_seconds", "Spec fetch duration")
pipeline_duration = metrics.histogram("pipeline_duration_seconds", "Pipeline execution duration")
active_repositories = metrics.gauge("active_repositories", "Number of active repositories")
