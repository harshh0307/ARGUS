from __future__ import annotations

# Patterns that could indicate prompt injection attempts
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
    """Sanitize file content before inserting into prompt.

    - Truncates to max_lines
    - Removes potential prompt injection patterns
    """
    lines = content.splitlines()

    # Truncate if too long
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines.append(f"... ({len(content.splitlines()) - max_lines} lines truncated)")

    # Remove potential prompt injection patterns
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
) -> str:
    """Build a structured prompt for the fix agent.

    Includes:
    - System role definition
    - Impact context
    - Sanitized code context
    - Clear output format
    - Retry context with error history
    """
    retry = ""
    if previous_error:
        retry = f"\nYour previous attempt failed. Fix the problem:\n{previous_error}\n"

    lang_hint = {
        "py": "Return valid Python.",
        "js": "Return valid JavaScript/TypeScript.",
    }.get(language, "Return syntactically valid code.")

    vendor_section = ""
    if vendor_guidance:
        vendor_section = (
            f"Vendor migration guidance (follow this when choosing the fix):\n"
            f"{vendor_guidance}\n"
        )

    # Sanitize the context
    sanitized_context = sanitize_content(context)

    return (
        "You are Argus, an automated API migration agent.\n"
        "Your task is to fix code that calls a deprecated or removed API endpoint.\n\n"
        "## API Change\n"
        f"[{impact['change_severity']}] {impact['change_kind']} "
        f"{impact['method'].upper()} {impact['path']}\n"
        f"Detail: {impact['change_detail']}\n\n"
        f"{vendor_section}"
        "## Call Site\n"
        f"File: {file_path} at line {impact['line']}\n"
        f"```\n{sanitized_context}\n```\n\n"
        "## Rules\n"
        "- Return exactly ONE PatchSuggestion\n"
        "- Only modify the line at the specified line number\n"
        "- Keep all surrounding code unchanged\n"
        "- For 'replace' action: provide the corrected single line of code\n"
        "- For 'remove' action: delete the line (set replacement to empty string)\n"
        "- If the endpoint was removed, rewrite to the replacement API if known, or remove the call\n"
        f"- {lang_hint}\n"
        "- Do NOT hallucinate endpoints that don't exist\n"
        "- Do NOT add new imports unless absolutely necessary\n"
        "- Do NOT change function signatures or class definitions\n"
        f"{retry}"
    )
