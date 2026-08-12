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


def validate_javascript(content: str) -> str | None:
    """Best-effort JS/TS syntax check: balanced braces/brackets/parens and
    quote-terminated strings. A full parser is out of scope; the semantic
    re-scan (endpoint still called) is the real guard."""
    stack: list[tuple[str, int]] = []
    pairs = {")": "(", "]": "[", "}": "{"}
    i = 0
    length = len(content)
    while i < length:
        ch = content[i]
        if ch in ("'", '"', "`"):
            i = _skip_string(content, i)
            if i >= length:
                return "unterminated string literal"
            continue
        if ch == "/" and i + 1 < length and content[i + 1] == "/":
            newline = content.find("\n", i)
            i = length if newline == -1 else newline + 1
            continue
        if ch == "/" and i + 1 < length and content[i + 1] == "*":
            end = content.find("*/", i + 2)
            if end == -1:
                return "unterminated block comment"
            i = end + 2
            continue
        if ch in "([{":
            stack.append((ch, i))
        elif ch in ")]}":
            if not stack or stack[-1][0] != pairs[ch]:
                return f"unbalanced {ch!r} at line {content.count(chr(10), 0, i) + 1}"
            stack.pop()
        i += 1
    if stack:
        ch, pos = stack[-1]
        return f"unbalanced {ch!r} opened at line {content.count(chr(10), 0, pos) + 1}"
    return None


def validate_source(content: str, language: str = "py") -> str | None:
    if language == "js":
        return validate_javascript(content)
    return validate_python(content)


def _skip_string(content: str, i: int) -> int:
    quote = content[i]
    i += 1
    length = len(content)
    while i < length:
        if content[i] == "\\":
            i += 2
            continue
        if content[i] == quote:
            return i + 1
        i += 1
    return length
