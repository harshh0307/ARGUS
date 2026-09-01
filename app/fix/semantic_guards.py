"""Deterministic semantic guards that re-scan patched code.

No LLM involved — pure pattern matching on the patched text.
These guards run AFTER a patch is applied and BEFORE it is written to disk.
They reject patches that claim to fix a change but don't actually address it.

Each guard takes (patched_content, impact_dict) and returns:
- None if the patch passes (no issues found)
- A string error message if the patch should be rejected
"""

from __future__ import annotations

import re
from collections.abc import Callable

from app.detection.models import ChangeKind

# ── Guard functions ─────────────────────────────────────────────────────────


def _guard_method_changed(content: str, impact: dict) -> str | None:
    """Reject if old HTTP method still called."""
    old = impact.get("old_method", "")
    if not old:
        return None
    patterns = [
        rf"\.{re.escape(old)}\s*\(",
        rf"""["']method["']\s*:\s*["']({re.escape(old)})["']""",
        rf"""\bmethod\s*=\s*["']({re.escape(old)})["']""",
    ]
    for pattern in patterns:
        if re.search(pattern, content, re.IGNORECASE):
            return f"Old method '{old}' still present in patched code"
    return None


def _guard_param_removed(content: str, impact: dict) -> str | None:
    """Reject if removed parameter still passed."""
    param = impact.get("param_name", "")
    if not param:
        return None
    if re.search(rf"{re.escape(param)}\s*=", content):
        return f"Removed parameter '{param}' still present"
    return None


def _guard_param_type_changed(content: str, impact: dict) -> str | None:
    """Reject if old type is still used without conversion."""
    new_type = impact.get("new_type", "")
    param = impact.get("param_name", "")
    if not new_type or not param:
        return None
    # Check if type conversion is present
    conversions = {
        "integer": r"\bint\s*\(",
        "number": r"\b(float|int)\s*\(",
        "string": r"\bstr\s*\(",
        "boolean": r"\bbool\s*\(",
    }
    pattern = conversions.get(new_type)
    if pattern and not re.search(pattern, content):
        return f"Type conversion to {new_type} not found for parameter '{param}'"
    return None


def _guard_enum_value_removed(content: str, impact: dict) -> str | None:
    """Reject if removed enum value still used."""
    old = impact.get("old_value", "")
    if not old:
        return None
    if re.search(rf"""['"]({re.escape(old)})['"]""", content):
        return f"Removed enum value '{old}' still present"
    return None


def _guard_response_code_removed(content: str, impact: dict) -> str | None:
    """Reject if removed status code still checked."""
    old = impact.get("old_value", "")
    if not old:
        return None
    if re.search(rf"(status|statusCode|status_code)\s*[=!]=?\s*{re.escape(str(old))}", content):
        return f"Removed status code {old} still checked"
    return None


def _guard_security_scheme_type_changed(content: str, impact: dict) -> str | None:
    """Reject if old auth pattern still present."""
    old_type = impact.get("old_value", "")
    if old_type == "http" and "Bearer" in content:
        return "Old Bearer auth pattern still present"
    if old_type == "apiKey" and re.search(r"""['"]api[_-]?key['"]""", content, re.IGNORECASE):
        return "Old API key pattern still present"
    if old_type == "oauth2" and "client_id" in content and "client_secret" in content:
        return "Old OAuth2 client credentials pattern still present"
    return None


def _guard_schema_property_removed(content: str, impact: dict) -> str | None:
    """Reject if removed property still accessed."""
    schema_path = impact.get("schema_path", "")
    prop_name = schema_path.split(".")[-1] if schema_path else ""
    if not prop_name:
        return None
    patterns = [
        rf"\.{re.escape(prop_name)}\b",
        rf"""['"]({re.escape(prop_name)})['"]""",
        rf"""\["({re.escape(prop_name)})"\]""",
    ]
    for pattern in patterns:
        if re.search(pattern, content):
            return f"Removed property '{prop_name}' still accessed"
    return None


def _guard_required_field_added(content: str, impact: dict) -> str | None:
    """Reject if new required field is not provided."""
    field_name = impact.get("field_name", "")
    if not field_name:
        return None
    # Check if the field is being set/provided
    if not re.search(rf"{re.escape(field_name)}\s*=", content):
        return f"New required field '{field_name}' not provided"
    return None


def _guard_body_removed(content: str, impact: dict) -> str | None:
    """Reject if request body still sent."""
    body_patterns = [
        r"json\s*=\s*\{",
        r"body\s*=\s*\{",
        r"data\s*=\s*\{",
        r"json\s*=\s*json\.dumps",
    ]
    for pattern in body_patterns:
        if re.search(pattern, content):
            return "Request body still present in patched code"
    return None


def _guard_oauth_scope_removed(content: str, impact: dict) -> str | None:
    """Reject if removed OAuth scope still requested."""
    scope = impact.get("old_value", "")
    if not scope:
        return None
    if re.search(rf"""['"]({re.escape(scope)})['"]""", content):
        return f"Removed OAuth scope '{scope}' still requested"
    return None


def _guard_endpoint_removed(content: str, impact: dict) -> str | None:
    """Reject if removed endpoint still called."""
    path = impact.get("path", "")
    if not path:
        return None
    # Convert path pattern to regex (e.g. /users/{id} → /users/[^/]+)
    path_pattern = re.escape(path).replace(r"\{[^}]+\}", r"[^/]+")
    if re.search(path_pattern, content):
        return f"Removed endpoint '{path}' still called"
    return None


# ── Registry ────────────────────────────────────────────────────────────────

SEMANTIC_GUARDS: dict[str, Callable[[str, dict], str | None]] = {
    ChangeKind.METHOD_CHANGED: _guard_method_changed,
    ChangeKind.PARAM_REMOVED: _guard_param_removed,
    ChangeKind.PARAM_TYPE_CHANGED: _guard_param_type_changed,
    ChangeKind.ENUM_VALUE_REMOVED: _guard_enum_value_removed,
    ChangeKind.RESPONSE_CODE_REMOVED: _guard_response_code_removed,
    ChangeKind.SECURITY_SCHEME_TYPE_CHANGED: _guard_security_scheme_type_changed,
    ChangeKind.SCHEMA_PROPERTY_REMOVED: _guard_schema_property_removed,
    ChangeKind.REQUIRED_FIELD_ADDED: _guard_required_field_added,
    ChangeKind.REQUEST_BODY_REMOVED: _guard_body_removed,
    ChangeKind.OAUTH_SCOPE_REMOVED: _guard_oauth_scope_removed,
    ChangeKind.ENDPOINT_REMOVED: _guard_endpoint_removed,
    ChangeKind.HTTP_METHOD_REMOVED: _guard_method_changed,
}


def run_semantic_guard(content: str, impact: dict) -> str | None:
    """Run the appropriate semantic guard for this change kind.

    Returns None if the patch passes, or an error message if rejected.
    """
    kind = impact.get("change_kind", "")
    guard = SEMANTIC_GUARDS.get(kind)
    if guard is None:
        return None  # no guard for this kind, accept
    return guard(content, impact)
