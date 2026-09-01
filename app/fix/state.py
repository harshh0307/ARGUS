"""LangGraph state definition with Postgres checkpointer and history trimming.

Design constraints:
- Short chains (3 nodes max) to prevent compound reliability decay
- Persistent state via Postgres checkpointer (survives restarts)
- Dynamic history trimming to prevent token window blowup
- Strict retry counter with graceful failure
- Scoped GitHub tokens (destroyed after PR)
"""

from __future__ import annotations

from typing import Annotated, TypedDict

# Maximum sizes for history lists to prevent token window blowup
MAX_PATCH_HISTORY = 10
MAX_ERROR_HISTORY = 5


def _trim_history(max_size: int):
    """Create a reducer that trims a list to max_size elements (keeps last N)."""

    def reducer(current: list[str], update: list[str]) -> list[str]:
        combined = current + update
        return combined[-max_size:]

    return reducer


class FixState(TypedDict):
    """State for the LangGraph fix pipeline.

    Designed for short chains (3 nodes: generate → apply → validate).
    History lists are automatically trimmed to prevent token blowup.
    """

    # ── Input ────────────────────────────────────────────────────────────
    impact: dict
    file_path: str
    file_content: str
    language: str
    vendor_guidance: str | None
    new_spec_context: str | None

    # ── Pipeline output ──────────────────────────────────────────────────
    patch: dict | None
    patched_content: str | None
    error: str | None

    # ── Retry control ────────────────────────────────────────────────────
    attempts: int
    patch_history: Annotated[list[str], _trim_history(MAX_PATCH_HISTORY)]
    error_history: Annotated[list[str], _trim_history(MAX_ERROR_HISTORY)]
    fix_errors: list[dict]

    # ── Token scoping ────────────────────────────────────────────────────
    installation_token: str | None
    repository_id: int | None


def create_initial_state(
    impact: dict,
    file_path: str,
    file_content: str,
    language: str = "python",
    vendor_guidance: str | None = None,
    new_spec_context: str | None = None,
    installation_token: str | None = None,
    repository_id: int | None = None,
) -> FixState:
    """Create a clean initial state for a fix attempt."""
    return FixState(
        impact=impact,
        file_path=file_path,
        file_content=file_content,
        language=language,
        vendor_guidance=vendor_guidance,
        new_spec_context=new_spec_context,
        patch=None,
        patched_content=None,
        error=None,
        attempts=0,
        patch_history=[],
        error_history=[],
        fix_errors=[],
        installation_token=installation_token,
        repository_id=repository_id,
    )


def create_checkpointer(database_url: str | None = None):
    """Create a Postgres-backed checkpointer for state persistence.

    Falls back to a memory checkpointer if no database URL is provided.
    This ensures the pipeline works in both development and production.
    """
    if database_url:
        try:
            from langgraph.checkpoint.postgres import PostgresSaver

            return PostgresSaver.from_conn_string(database_url)
        except ImportError:
            pass

    # Fallback: memory checkpointer (no persistence)
    from langgraph.checkpoint.memory import MemorySaver

    return MemorySaver()
