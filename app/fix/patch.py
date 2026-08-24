from __future__ import annotations

import ast
import re

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
        tree = ast.parse(content)
    except SyntaxError as exc:
        return f"SyntaxError at line {exc.lineno}: {exc.msg}"
    return _check_unreachable(tree)


def _check_unreachable(tree: ast.Module) -> str | None:
    """Detect unreachable code after raise/return/break/continue."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            err = _check_body_unreachable(node.body)
            if err:
                return err
        if isinstance(node, ast.For):
            err = _check_body_unreachable(node.body)
            if err:
                return err
            err = _check_body_unreachable(node.orelse)
            if err:
                return err
        if isinstance(node, ast.While):
            err = _check_body_unreachable(node.body)
            if err:
                return err
        if isinstance(node, ast.If):
            err = _check_body_unreachable(node.body)
            if err:
                return err
            err = _check_body_unreachable(node.orelse)
            if err:
                return err
        if isinstance(node, ast.With):
            err = _check_body_unreachable(node.body)
            if err:
                return err
        if isinstance(node, ast.Try):
            err = _check_body_unreachable(node.body)
            if err:
                return err
            for handler in node.handlers:
                err = _check_body_unreachable(handler.body)
                if err:
                    return err
            err = _check_body_unreachable(node.finalbody)
            if err:
                return err
    return None


def _check_body_unreachable(body: list[ast.stmt]) -> str | None:
    """Check for unreachable code within a list of statements."""
    _TERMINAL = (ast.Raise, ast.Return, ast.Break, ast.Continue)
    for i, stmt in enumerate(body):
        if isinstance(stmt, _TERMINAL):
            for next_stmt in body[i + 1:]:
                if isinstance(next_stmt, _TERMINAL):
                    return f"Unreachable code after {type(stmt).__name__.lower()} at line {getattr(stmt, 'lineno', '?')}: line {getattr(next_stmt, 'lineno', '?')}"
                if isinstance(next_stmt, (ast.Expr, ast.Assign, ast.AugAssign, ast.AnnAssign)):
                    return f"Unreachable code after {type(stmt).__name__.lower()} at line {getattr(stmt, 'lineno', '?')}: line {getattr(next_stmt, 'lineno', '?')}"
    return None


def validate_javascript(content: str) -> str | None:
    """Best-effort JS/TS syntax check: balanced braces/brackets/parens,
    quote-terminated strings, and common structural errors."""
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
    err = _check_js_throw_patterns(content)
    if err:
        return err
    return None


def _check_js_throw_patterns(content: str) -> str | None:
    """Detect throw statements used in expression context (not as standalone statements)."""
    lines = content.split("\n")
    for line_no, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith(("//", "/*")):
            continue
        # throw used as IIFE return value: (() => { throw ... })()
        if re.search(r"\(\s*\(\s*\)\s*=>\s*\{[^}]*throw\s+new\s+", stripped):
            return f"throw in arrow IIFE used as expression at line {line_no}"
        # throw in async IIFE: await (async () => { throw ... })()
        if re.search(r"await\s*\(\s*async\s*\(\s*\)\s*=>\s*\{[^}]*throw\s+new\s+", stripped):
            return f"throw in async IIFE used as expression at line {line_no}"
        # throw after assignment: const x = null; throw
        if re.search(r"=\s*(?:null|undefined|false|true|0|\[\]|\{{\}})\s*;\s*throw\s+new\s+Error", stripped):
            return f"throw after dummy assignment at line {line_no}"
        # throw in logical expression: expr && throw / expr || throw
        if re.search(r"(?:&&|\|\|)\s*throw\s+new\s+Error", stripped):
            return f"throw in logical expression at line {line_no}"
        # throw in comma expression: (expr, throw)
        if re.search(r",\s*throw\s+new\s+Error", stripped):
            return f"throw in comma expression at line {line_no}"
        # throw as function argument: func(throw ...)
        if re.search(r"\w+\s*\(\s*throw\s+new\s+Error", stripped):
            return f"throw as function argument at line {line_no}"
        # throw used as value in template literal or concatenation
        if re.search(r"[`+].*throw\s+new\s+Error", stripped):
            return f"throw in string expression at line {line_no}"
    return None


def validate_source(content: str, language: str = "py") -> str | None:
    if language in ("js", "ts", "tsx", "jsx", "mjs", "cjs"):
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
