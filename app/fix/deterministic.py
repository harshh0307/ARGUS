from __future__ import annotations

import re

from app.fix.ast_validators import validate_source
from app.fix.strategies import get_strategy


def try_deterministic_fix(
    impact: dict,
    file_content: str,
    language: str,
) -> tuple[str | None, str | None]:
    """Try to fix without LLM using regex patterns and validators.

    Returns (patched_content, error). If no deterministic fix is possible,
    returns (None, error_message).
    """
    change_kind = impact.get("change_kind", "")
    strategy = get_strategy(change_kind)

    if strategy is None:
        return None, f"no strategy for {change_kind}"

    if strategy.llm_required:
        return None, "strategy requires LLM"

    if not strategy.pattern:
        return None, "no deterministic pattern available"

    match = _find_match(strategy.pattern, file_content, impact.get("line", 0))
    if match is None:
        return None, "pattern not found in source"

    replacement = _apply_template(strategy.replacement_template, match, impact)
    if replacement is None:
        return None, "could not apply replacement template"

    patched = file_content[:match.start()] + replacement + file_content[match.end():]

    syntax_err = validate_source(patched, language)
    if syntax_err:
        return None, f"syntax validation failed: {syntax_err}"

    if strategy.validator:
        val_err = strategy.validator(patched, impact)
        if val_err:
            return None, f"strategy validation failed: {val_err}"

    if strategy.guard:
        guard_err = strategy.guard(patched, impact)
        if guard_err:
            return None, f"guard failed: {guard_err}"

    return patched, None


def _find_match(pattern: str, content: str, target_line: int) -> re.Match | None:
    """Find the best regex match, preferring the one nearest target_line."""
    matches = list(re.finditer(pattern, content, re.MULTILINE))
    if not matches:
        return None

    if target_line <= 0:
        return matches[0]

    best = None
    best_dist = float("inf")
    for m in matches:
        line_num = content[:m.start()].count("\n") + 1
        dist = abs(line_num - target_line)
        if dist < best_dist:
            best_dist = dist
            best = m

    return best or matches[0]


def _apply_template(template: str, match: re.Match, impact: dict) -> str | None:
    """Apply a replacement template with variable substitution."""
    if template is None:
        return None

    result = template

    old_value = match.group(0)
    result = result.replace("{old}", old_value)
    result = result.replace("{new}", old_value)

    for key, value in impact.items():
        if isinstance(value, str):
            result = result.replace(f"{{{key}}}", value)

    return result
