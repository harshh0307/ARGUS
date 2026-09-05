from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class TelemetryEvent:
    vendor_slug: str
    endpoint: str
    method: str
    path: str
    status_code: int
    drift_detected: bool = False
    drift_details: dict | None = None
    response_schema_hash: str | None = None
    request_body_hash: str | None = None
    captured_at: datetime | None = None
    tenant_id: str | None = None


@dataclass
class DriftSignal:
    vendor_slug: str
    endpoint: str
    drift_type: str  # schema_drift | error_spike | response_mismatch
    severity: str  # breaking | warning
    details: dict = field(default_factory=dict)
    detected_at: datetime | None = None


@dataclass
class DriftAlert:
    id: int | None = None
    vendor_slug: str = ""
    alert_type: str = ""
    severity: str = ""
    endpoint: str | None = None
    details: dict = field(default_factory=dict)
    investigation_id: int | None = None
    resolved: bool = False
    created_at: datetime | None = None
    tenant_id: str | None = None
