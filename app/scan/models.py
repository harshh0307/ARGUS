from dataclasses import dataclass

from app.detection.models import Change


@dataclass(frozen=True)
class Usage:
    file: str
    line: int
    method: str
    path: str

    def __str__(self) -> str:
        return f"{self.file}:{self.line} calls {self.method.upper()} {self.path}"


@dataclass(frozen=True)
class HeaderUsage:
    file: str
    line: int
    header_name: str
    header_value: str | None
    context: str

    def __str__(self) -> str:
        return f"{self.file}:{self.line} sets header '{self.header_name}' ({self.context})"


@dataclass(frozen=True)
class Impact:
    usage: Usage
    change: Change

    def __str__(self) -> str:
        return f"{self.usage.file}:{self.usage.line} affected by [{self.change.severity}] {self.change.kind}"
