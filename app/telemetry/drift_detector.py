from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.config import Settings
from app.telemetry.models import DriftSignal


class DriftDetector:
    """Compares response schemas against known baselines to detect drift."""

    def __init__(self, vendor_slug: str, settings: Settings):
        self.vendor_slug = vendor_slug
        self.settings = settings
        self._baseline_schemas: dict[str, dict] = {}
        self._error_counts: dict[str, list[datetime]] = defaultdict(list)

    def check(self, endpoint: str, status_code: int, body: Any = None) -> DriftSignal | None:
        schema_drift = self._check_schema_drift(endpoint, status_code, body)
        if schema_drift:
            return schema_drift

        error_spike = self._check_error_spike(endpoint, status_code)
        if error_spike:
            return error_spike

        return None

    def _check_schema_drift(
        self, endpoint: str, status_code: int, body: Any
    ) -> DriftSignal | None:
        if status_code >= 400 or body is None:
            return None

        try:
            if isinstance(body, str):
                body = json.loads(body)
        except (json.JSONDecodeError, TypeError):
            return None

        if not isinstance(body, (dict, list)):
            return None

        current_schema = self._extract_schema(body)
        baseline = self._baseline_schemas.get(endpoint)

        if baseline is None:
            self._baseline_schemas[endpoint] = current_schema
            return None

        diff = self._diff_schemas(baseline, current_schema)
        if diff and self._is_significant(diff):
            return DriftSignal(
                vendor_slug=self.vendor_slug,
                endpoint=endpoint,
                drift_type="schema_drift",
                severity="breaking" if diff.get("removed_fields") else "warning",
                details=diff,
                detected_at=datetime.now(UTC),
            )

        return None

    def _check_error_spike(self, endpoint: str, status_code: int) -> DriftSignal | None:
        now = datetime.now(UTC)
        if status_code >= 400:
            self._error_counts[endpoint].append(now)

        cutoff = now - timedelta(minutes=5)
        self._error_counts[endpoint] = [
            t for t in self._error_counts[endpoint] if t > cutoff
        ]

        count = len(self._error_counts[endpoint])
        threshold = self.settings.telemetry_error_spike_threshold
        if count >= threshold:
            return DriftSignal(
                vendor_slug=self.vendor_slug,
                endpoint=endpoint,
                drift_type="error_spike",
                severity="breaking",
                details={"error_count": count, "window_minutes": 5, "threshold": threshold},
                detected_at=now,
            )

        return None

    def _extract_schema(self, data: Any) -> dict:
        if isinstance(data, dict):
            return {
                "type": "object",
                "properties": {k: self._extract_schema(v) for k, v in data.items()},
                "required": list(data.keys()),
            }
        if isinstance(data, list):
            if data:
                return {"type": "array", "items": self._extract_schema(data[0])}
            return {"type": "array", "items": {}}
        if isinstance(data, bool):
            return {"type": "boolean"}
        if isinstance(data, int):
            return {"type": "integer"}
        if isinstance(data, float):
            return {"type": "number"}
        if isinstance(data, str):
            return {"type": "string"}
        return {"type": "null"}

    def _diff_schemas(self, baseline: dict, current: dict) -> dict:
        diff: dict[str, Any] = {}

        base_props = baseline.get("properties", {})
        curr_props = current.get("properties", {})

        removed = set(base_props.keys()) - set(curr_props.keys())
        added = set(curr_props.keys()) - set(base_props.keys())
        changed = []

        for key in set(base_props.keys()) & set(curr_props.keys()):
            if base_props[key].get("type") != curr_props[key].get("type"):
                changed.append({
                    "field": key,
                    "old_type": base_props[key].get("type"),
                    "new_type": curr_props[key].get("type"),
                })

        if removed:
            diff["removed_fields"] = list(removed)
        if added:
            diff["added_fields"] = list(added)
        if changed:
            diff["type_changes"] = changed

        return diff

    def _is_significant(self, diff: dict) -> bool:
        if "removed_fields" in diff:
            return True
        if "type_changes" in diff:
            return True
        return False

    def load_baseline(self, endpoint: str, schema: dict) -> None:
        self._baseline_schemas[endpoint] = schema
