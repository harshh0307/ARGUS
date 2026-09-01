"""Deterministic AST-based syntax validation for all supported languages.

No LLM involved — pure syntax checking.
Used by the fix agent to reject patches that break syntax before
ever reaching the semantic guard or the LLM.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path


def validate_python(content: str) -> tuple[bool, str | None]:
    """Validate Python syntax using ast.parse + unreachable code check."""
    try:
        tree = ast.parse(content)
        _check_python_unreachable(tree)
        return True, None
    except SyntaxError as e:
        return False, f"Line {e.lineno}: {e.msg}"


def _check_python_unreachable(tree: ast.Module) -> None:
    """Walk AST to find unreachable code after terminal statements."""
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            _check_body_unreachable(node.body)


def _check_body_unreachable(body: list) -> None:
    """Check for unreachable statements after return/raise/break/continue."""
    found_terminal = False
    for stmt in body:
        if found_terminal:
            raise SyntaxError(
                f"Unreachable code after terminal statement at line {stmt.lineno}"
            )
        if isinstance(stmt, (ast.Return, ast.Raise, ast.Break, ast.Continue)):
            found_terminal = True


def validate_javascript(content: str) -> tuple[bool, str | None]:
    """Best-effort JS/TS syntax validation using brace matching."""
    stack = []
    in_string = False
    string_char = None
    escape_next = False
    in_template = False
    template_depth = 0

    for i, ch in enumerate(content):
        if escape_next:
            escape_next = False
            continue
        if ch == "\\":
            escape_next = True
            continue

        if in_string:
            if ch == string_char:
                in_string = False
            continue

        if ch in ('"', "'"):
            in_string = True
            string_char = ch
            continue

        if ch == "`":
            if in_template:
                template_depth -= 1
                if template_depth == 0:
                    in_template = False
            else:
                in_template = True
                template_depth += 1
            continue

        if in_template:
            continue

        # Line/block comments
        if ch == "/" and i + 1 < len(content):
            next_ch = content[i + 1]
            if next_ch == "/":
                # Skip to end of line
                newline = content.find("\n", i)
                if newline == -1:
                    break
                continue
            if next_ch == "*":
                # Skip to */
                end = content.find("*/", i + 2)
                if end == -1:
                    break
                continue

        if ch in ("{", "(", "["):
            stack.append(ch)
        elif ch in ("}", ")", "]"):
            expected = {"}": "{", ")": "(", "]": "["}[ch]
            if not stack or stack[-1] != expected:
                return False, f"Unmatched '{ch}' at position {i}"
            stack.pop()

    if stack:
        return False, f"Unclosed '{stack[-1]}' at end of file"

    # Check for common syntax issues
    if re.search(r"^\s*else\s+if\b", content, re.MULTILINE):
        return False, "Use 'else if' instead of 'elseif' (if this is PHP)"

    return True, None


def validate_go(content: str) -> tuple[bool, str | None]:
    """Validate Go syntax: balanced braces + package declaration."""
    ok, err = _validate_braces(content)
    if not ok:
        return False, err
    if not re.search(r"^package\s+\w+", content, re.MULTILINE):
        return False, "Missing package declaration"
    return True, None


def validate_ruby(content: str) -> tuple[bool, str | None]:
    """Validate Ruby syntax: balanced block openers vs end keywords."""
    # Strip strings and comments first
    stripped = re.sub(r'#.*$', "", content, flags=re.MULTILINE)
    stripped = re.sub(r'"[^"]*"', '""', stripped)
    stripped = re.sub(r"'[^']*'", "''", stripped)

    openers = len(
        re.findall(
            r"\b(do|if|unless|while|until|class|module|def|begin|case)\b", stripped
        )
    )
    ends = len(re.findall(r"\bend\b", stripped))

    # Handle inline if/unless (no end needed)
    len(re.findall(r"\bif\b.*$", stripped, re.MULTILINE))
    if openers != ends:
        # Adjust for inline conditionals
        diff = openers - ends
        if diff > 0:
            return False, f"Mismatched block openers ({openers}) vs end ({ends})"
    return True, None


def validate_java(content: str) -> tuple[bool, str | None]:
    """Validate Java syntax: balanced braces + class declaration."""
    ok, err = _validate_braces(content)
    if not ok:
        return False, err
    if not re.search(
        r"(public|private|protected|abstract|final)?\s*(class|interface|enum|record)\s+\w+",
        content,
    ):
        return False, "Missing class/interface/enum declaration"
    return True, None


def validate_php(content: str) -> tuple[bool, str | None]:
    """Validate PHP syntax: balanced braces + optional opening tag."""
    ok, err = _validate_braces(content)
    if not ok:
        return False, err
    return True, None


def validate_csharp(content: str) -> tuple[bool, str | None]:
    """Validate C# syntax: balanced braces + namespace/class."""
    ok, err = _validate_braces(content)
    if not ok:
        return False, err
    return True, None


def _validate_braces(content: str) -> tuple[bool, str | None]:
    """Shared brace/bracket/paren balance check."""
    stack = []
    in_string = False
    string_char = None
    escape_next = False

    for i, ch in enumerate(content):
        if escape_next:
            escape_next = False
            continue
        if ch == "\\":
            escape_next = True
            continue

        if in_string:
            if ch == string_char:
                in_string = False
            continue

        if ch in ('"', "'"):
            in_string = True
            string_char = ch
            continue

        if ch in ("{", "(", "["):
            stack.append(ch)
        elif ch in ("}", ")", "]"):
            expected = {"}": "{", ")": "(", "]": "["}[ch]
            if not stack or stack[-1] != expected:
                return False, f"Unmatched '{ch}' at position {i}"
            stack.pop()

    if stack:
        return False, f"Unclosed '{stack[-1]}' at end of file"

    return True, None


# ── Registry ────────────────────────────────────────────────────────────────

_VALIDATORS: dict[str, callable] = {
    ".py": validate_python,
    ".js": validate_javascript,
    ".ts": validate_javascript,
    ".jsx": validate_javascript,
    ".tsx": validate_javascript,
    ".go": validate_go,
    ".rb": validate_ruby,
    ".java": validate_java,
    ".php": validate_php,
    ".cs": validate_csharp,
}


def validate_source(content: str, file_path: str) -> tuple[bool, str | None]:
    """Dispatch to the appropriate language validator.

    Returns (is_valid, error_message).
    For unknown file extensions, returns (True, None) — skip validation.
    """
    ext = Path(file_path).suffix.lower()
    validator = _VALIDATORS.get(ext)
    if validator is None:
        return True, None  # unknown language, skip
    return validator(content)
