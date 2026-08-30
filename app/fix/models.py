from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel


class PatchSuggestion(BaseModel):
    file: str
    line: int
    action: Literal["replace", "remove", "insert"] = "replace"
    replacement: str = ""
    end_line: int | None = None
    content: str | None = None


@dataclass(frozen=True)
class FixResult:
    file: str
    line: int
    success: bool
    patch: PatchSuggestion | None = None
    error: str | None = None
