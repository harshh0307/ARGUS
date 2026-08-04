from __future__ import annotations

import ast

from app.fix.models import PatchSuggestion


def apply_patch(content: str, patch: PatchSuggestion) -> tuple[str | None, str | None]:
    lines = content.splitlines()
    if not (1 <= patch.line <= len(lines)):
        return None, f"line {patch.line} out of range (file has {len(lines)} lines)"
    if patch.action == "remove":
        del lines[patch.line - 1]
    elif not patch.replacement:
        return None, "replacement is empty"
    else:
        lines[patch.line - 1] = patch.replacement
    new_content = "\n".join(lines)
    if content.endswith("\n"):
        new_content += "\n"
    return new_content, None


def validate_python(content: str) -> str | None:
    try:
        ast.parse(content)
    except SyntaxError as exc:
        return f"SyntaxError at line {exc.lineno}: {exc.msg}"
    return None
