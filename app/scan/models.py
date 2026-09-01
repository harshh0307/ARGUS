from __future__ import annotations

from dataclasses import dataclass

from app.detection.models import Change


@dataclass(frozen=True)
class Usage:
    """Tracks an API call site in source code (method + path)."""

    file: str
    line: int
    method: str
    path: str

    def __str__(self) -> str:
        return f"{self.file}:{self.line} calls {self.method.upper()} {self.path}"


@dataclass(frozen=True)
class HeaderUsage:
    """Tracks a header being set in source code."""

    file: str
    line: int
    header_name: str
    header_value: str | None
    context: str

    def __str__(self) -> str:
        return f"{self.file}:{self.line} sets header '{self.header_name}' ({self.context})"


@dataclass(frozen=True)
class BodyUsage:
    """Tracks which request body fields a code file accesses."""

    file: str
    line: int
    method: str
    path: str
    fields_used: tuple[str, ...] = ()
    content_type: str | None = None

    def __str__(self) -> str:
        fields = ", ".join(self.fields_used) if self.fields_used else "(no fields)"
        return f"{self.file}:{self.line} sends body fields [{fields}] to {self.method.upper()} {self.path}"


@dataclass(frozen=True)
class AuthUsage:
    """Tracks authentication patterns in code."""

    file: str
    line: int
    auth_type: str  # "bearer", "api_key", "oauth2", "basic"
    header_name: str | None = None
    param_name: str | None = None  # for query-param API keys
    scope_used: tuple[str, ...] | None = None

    def __str__(self) -> str:
        return f"{self.file}:{self.line} uses {self.auth_type} auth"


@dataclass(frozen=True)
class ResponseUsage:
    """Tracks how code consumes API responses."""

    file: str
    line: int
    method: str
    path: str
    status_codes_used: tuple[str, ...] = ()
    fields_used: tuple[str, ...] = ()

    def __str__(self) -> str:
        codes = ", ".join(self.status_codes_used) if self.status_codes_used else "(any)"
        return f"{self.file}:{self.line} handles {self.method.upper()} {self.path} responses [{codes}]"


# Union of all usage types for Impact
AnyUsage = Usage | BodyUsage | AuthUsage | ResponseUsage | HeaderUsage


@dataclass(frozen=True)
class Impact:
    """Links a code usage to a spec change that affects it."""

    usage: AnyUsage
    change: Change

    def __str__(self) -> str:
        return f"{self.usage.file}:{self.usage.line} affected by [{self.change.severity}] {self.change.kind}"
