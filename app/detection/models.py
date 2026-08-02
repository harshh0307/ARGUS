from dataclasses import dataclass

BREAKING = "breaking"
ADDITIVE = "additive"


@dataclass(frozen=True)
class Change:
    kind: str
    severity: str
    path: str
    method: str
    detail: str = ""

    def __str__(self) -> str:
        return f"[{self.severity}] {self.method.upper()} {self.path} - {self.kind}: {self.detail}"
