from __future__ import annotations


class ContextBuilder:
    """Builds fix context from investigation findings for the fix agent."""

    def build(
        self,
        drift_details: dict,
        changelog_snippets: list[str] | None = None,
        doc_references: list[str] | None = None,
    ) -> str:
        parts = []

        parts.append("## What Changed")
        parts.append(self._format_drift(drift_details))

        if changelog_snippets:
            parts.append("\n## Vendor Changelog")
            for i, snippet in enumerate(changelog_snippets[:5], 1):
                parts.append(f"{i}. {snippet[:500]}")

        if doc_references:
            parts.append("\n## Related Documentation")
            for ref in doc_references[:5]:
                parts.append(f"- {ref}")

        return "\n".join(parts)

    def _format_drift(self, drift_details: dict) -> str:
        lines = []
        drift_type = drift_details.get("drift_type", "unknown")
        lines.append(f"Drift type: {drift_type}")

        details = drift_details.get("details", {})

        if "removed_fields" in details:
            lines.append(f"Removed fields: {', '.join(details['removed_fields'])}")

        if "added_fields" in details:
            lines.append(f"Added fields: {', '.join(details['added_fields'])}")

        if "type_changes" in details:
            for tc in details["type_changes"]:
                lines.append(
                    f"Field '{tc.get('field', '')}' type changed "
                    f"from {tc.get('old_type', '?')} to {tc.get('new_type', '?')}"
                )

        if "error_count" in details:
            lines.append(
                f"Error spike: {details['error_count']} errors in "
                f"the last {details.get('window_minutes', 5)} minutes"
            )

        return "\n".join(lines)
