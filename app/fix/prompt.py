from __future__ import annotations

_INJECTION_PATTERNS = [
    "ignore previous",
    "ignore all previous",
    "you are now",
    "system:",
    "assistant:",
    "human:",
    "new instructions",
    "override",
    "disregard",
    "forget everything",
    "act as",
    "pretend you are",
    "roleplay as",
]


def sanitize_content(content: str, max_lines: int = 200) -> str:
    """Sanitize file content before inserting into prompt."""
    lines = content.splitlines()
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines.append(f"... ({len(content.splitlines()) - max_lines} lines truncated)")
    sanitized = []
    for line in lines:
        lower = line.lower().strip()
        if any(pattern in lower for pattern in _INJECTION_PATTERNS):
            continue
        sanitized.append(line)
    return "\n".join(sanitized)


def build_prompt(
    impact: dict,
    file_path: str,
    context: str,
    previous_error: str | None = None,
    language: str = "py",
    vendor_guidance: str | None = None,
    new_spec_context: str | None = None,
) -> str:
    retry = ""
    if previous_error:
        retry = f"\nYour previous attempt failed. Fix the problem:\n{previous_error}\n"

    lang_hint = {
        "py": "Return valid Python.",
        "js": "Return valid JavaScript/TypeScript.",
        "go": "Return valid Go.",
        "ruby": "Return valid Ruby.",
        "java": "Return valid Java.",
        "php": "Return valid PHP.",
        "cs": "Return valid C#.",
    }.get(language, "Return syntactically valid code.")

    vendor_section = ""
    if vendor_guidance:
        vendor_section = (
            f"Vendor migration guidance (follow this when choosing the fix):\n"
            f"{vendor_guidance}\n"
        )

    spec_section = ""
    if new_spec_context:
        spec_section = (
            f"New API endpoint definition:\n"
            f"```\n{new_spec_context}\n```\n\n"
        )

    sanitized_context = sanitize_content(context)

    return (
        "You are Argus, an automated API migration agent.\n"
        "Your task is to fix code that calls a deprecated or removed API endpoint.\n\n"
        "## API Change\n"
        f"[{impact['change_severity']}] {impact['change_kind']} "
        f"{impact['method'].upper()} {impact['path']}\n"
        f"Detail: {impact['change_detail']}\n\n"
        f"{vendor_section}"
        f"{spec_section}"
        "## Call Site\n"
        f"File: {file_path} at line {impact['line']}\n"
        f"```\n{sanitized_context}\n```\n\n"
        "## Rules\n"
        "- Return exactly ONE PatchSuggestion\n"
        "- You may modify a single line OR multiple consecutive lines if needed\n"
        "- Use 'replace' action with end_line for multi-line changes\n"
        "- Use 'insert' action to add new lines before the target line\n"
        "- Keep all surrounding code unchanged\n"
        "- For 'replace' action: provide the corrected code\n"
        "- For 'remove' action: delete the line(s) (set replacement to empty string)\n"
        "- If the endpoint was removed, rewrite to the replacement API if known, or remove the call\n"
        f"- {lang_hint}\n"
        "- Do NOT hallucinate endpoints that don't exist\n"
        "- Do NOT add new imports unless absolutely necessary\n"
        "- Do NOT change function signatures or class definitions\n"
        f"{retry}"
    )
