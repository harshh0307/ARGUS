from __future__ import annotations

from app.fix.models import PatchSuggestion


class PatchValidationError(Exception):
    """Raised when a patch fails validation."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


class PatchValidator:
    """Validates LLM-generated patches against the original content and impact."""

    def validate(
        self,
        patch: PatchSuggestion,
        original_content: str,
        impact: dict,
    ) -> list[str]:
        """Validate a patch and return list of errors (empty = valid)."""
        errors: list[str] = []

        # 1. File path must match
        if patch.file != impact.get("file"):
            errors.append(
                f"file mismatch: expected {impact.get('file')!r}, got {patch.file!r}"
            )

        # 2. Line number must be in range
        lines = original_content.splitlines()
        if not lines:
            errors.append("original content is empty")
            return errors

        if not (1 <= patch.line <= len(lines)):
            errors.append(
                f"line {patch.line} out of range (file has {len(lines)} lines)"
            )
            return errors  # Can't validate further

        # 3. Line number should match impact line (warning, not fatal)
        if patch.line != impact.get("line"):
            errors.append(
                f"line mismatch: impact at line {impact.get('line')}, patch at line {patch.line}"
            )

        # 4. Action-specific validation
        if patch.action == "replace":
            if not patch.replacement:
                errors.append("replacement is empty")
            else:
                end = patch.end_line or patch.line
                if end != patch.line:
                    if not (1 <= end <= len(lines)):
                        errors.append(f"end_line {end} out of range")
                else:
                    original_line = lines[patch.line - 1].strip()
                    replacement = patch.replacement.strip()
                    if original_line == replacement:
                        errors.append("replacement is identical to original line")

                    original_len = len(lines[patch.line - 1])
                    replacement_len = len(patch.replacement)
                    if replacement_len > original_len * 5:
                        errors.append(
                            f"replacement is {replacement_len / original_len:.1f}x longer than original"
                        )

        elif patch.action == "remove":
            end = patch.end_line or patch.line
            if end != patch.line:
                if not (1 <= end <= len(lines)):
                    errors.append(f"end_line {end} out of range")
            elif len(lines) == 1:
                errors.append("removing the only line in a file")

        elif patch.action == "insert":
            insert_text = patch.content or patch.replacement
            if not insert_text:
                errors.append("insert content is empty")

        else:
            errors.append(f"unknown action: {patch.action!r}")

        return errors

    def validate_or_raise(
        self,
        patch: PatchSuggestion,
        original_content: str,
        impact: dict,
    ) -> None:
        """Validate and raise PatchValidationError if invalid."""
        errors = self.validate(patch, original_content, impact)
        if errors:
            raise PatchValidationError(errors)


def validate_patch_diff(
    original: str,
    patched: str,
    impact: dict,
) -> str | None:
    """Validate that a diff is minimal and correct.

    Returns error message if invalid, None if valid.
    """
    original_lines = original.splitlines()
    patched_lines = patched.splitlines()

    if len(patched_lines) < len(original_lines) - 1:
        return f"too many lines removed: {len(original_lines)} -> {len(patched_lines)}"

    if len(patched_lines) > len(original_lines) + 1:
        return f"too many lines added: {len(original_lines)} -> {len(patched_lines)}"

    # Find changed lines
    changed_lines: list[int] = []
    for i, (old, new) in enumerate(zip(original_lines, patched_lines)):
        if old != new:
            changed_lines.append(i + 1)

    if not changed_lines:
        return "no changes made"

    # For a single line patch, exactly one line should change
    target_line = impact.get("line")
    if target_line and target_line not in changed_lines:
        return f"impact line {target_line} not changed; changed lines: {changed_lines}"

    return None
