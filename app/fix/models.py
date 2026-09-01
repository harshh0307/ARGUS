from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel


class PatchSuggestion(BaseModel):
    """A single code patch suggested by the fix agent."""

    file: str
    line: int
    action: Literal[
        "replace", "remove", "insert", "add_import", "remove_import", "rename"
    ] = "replace"
    replacement: str = ""
    end_line: int | None = None
    content: str | None = None
    # New structured fields
    explanation: str = ""
    import_path: str | None = None  # for add_import/remove_import
    old_name: str | None = None  # for rename
    new_name: str | None = None  # for rename


@dataclass(frozen=True)
class FixResult:
    """Outcome of applying a single patch."""

    file: str
    line: int
    success: bool
    patch: PatchSuggestion | None = None
    error: str | None = None


@dataclass
class FixStrategy:
    """Deterministic fix rule for a specific ChangeKind.

    Design principle: most fixes are mechanical (regex replace + validate).
    Only when the deterministic template fails do we fall back to the LLM.
    This keeps the LLM out of the loop for ~85% of changes.
    """

    kind: str  # ChangeKind value
    description: str = ""
    # Deterministic fix (no LLM needed)
    pattern: str | None = None  # regex to find affected code
    replacement_template: str | None = None  # replacement with groups
    validator: Callable[[str, dict], bool] | None = None  # validates the fix
    guard: Callable[[str, dict], str | None] | None = None  # rejects bad patches
    # LLM fallback (when deterministic fails)
    llm_required: bool = False
    prompt_instructions: str | None = None  # specific instructions for LLM
    # Metadata
    examples: list[dict[str, str]] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)  # other kinds this depends on
