from __future__ import annotations


def build_prompt(
    impact: dict,
    file_path: str,
    context: str,
    previous_error: str | None = None,
) -> str:
    retry = ""
    if previous_error:
        retry = f"\nYour previous attempt failed. Fix the problem:\n{previous_error}\n"
    return (
        "You are Argus, an automated API migration agent.\n"
        "The API change affecting this code:\n"
        f"[{impact['change_severity']}] {impact['change_kind']} "
        f"{impact['method'].upper()} {impact['path']}\n"
        f"Detail: {impact['change_detail']}\n\n"
        f"The call site is in {file_path} at line {impact['line']}:\n"
        f"{context}\n"
        "Produce ONE PatchSuggestion that fixes the call site.\n"
        "Rules:\n"
        "- Only touch the affected line; keep all surrounding code unchanged.\n"
        "- action 'replace' with the corrected single line of code.\n"
        "- If the endpoint was removed, rewrite the call to the replacement API "
        "if you know it, or set action 'remove' to delete the line.\n"
        "- Return valid Python.\n"
        f"{retry}"
    )
