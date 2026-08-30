from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

BREAKING = "breaking"
ADDITIVE = "additive"
DEPRECATION = "deprecation"
WARNING = "warning"


@dataclass(frozen=True)
class Change:
    kind: str
    severity: str
    path: str
    method: str
    detail: str = ""
    old_value: Any | None = field(default=None, repr=False)
    new_value: Any | None = field(default=None, repr=False)
    schema_path: str | None = None
    ref_source: str | None = None

    def __str__(self) -> str:
        return f"[{self.severity}] {self.method.upper()} {self.path} - {self.kind}: {self.detail}"
