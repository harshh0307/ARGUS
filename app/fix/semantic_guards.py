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


# ── Additional semantic guards ──────────────────────────────────────────────

def _guard_param_required(content: str, impact: dict) -> str | None:
    """Ensure new required parameter is actually present in the call."""
    param_name = impact.get("new_value") or impact.get("detail", "").split("'")[1] if "'" in impact.get("detail", "") else None
    if not param_name:
        return None
    if param_name in content:
        return None
    return f"new required parameter '{param_name}' not found in patched code"


def _guard_request_body_added(content: str, impact: dict) -> str | None:
    """Ensure request body is now being sent when body was added."""
    body_indicators = ["json=", "data=", "body=", "json:", "body:", "data:", "FormUrlEncodedContent", "MultiValueMap"]
    for indicator in body_indicators:
        if indicator in content:
            return None
    return "request body was added but no body content found in patched code"


def _guard_request_body_required_changed(content: str, impact: dict) -> str | None:
    """Ensure body presence matches the new required status."""
    is_required = impact.get("new_value") is True or impact.get("new_value") == "true"
    body_indicators = ["json=", "data=", "body=", "json:", "body:", "data:"]
    has_body = any(ind in content for ind in body_indicators)
    if is_required and not has_body:
        return "request body is now required but no body content found in patched code"
    return None


def _guard_response_schema_removed(content: str, impact: dict) -> str | None:
    """Ensure response handling block is updated when schema is removed."""
    response_indicators = [".json()", ".text", ".content", "response.", "resp.", "res."]
    has_response_access = any(ind in content for ind in response_indicators)
    if has_response_access:
        return "response schema was removed but response body is still being accessed"
    return None


def _guard_schema_type_changed(content: str, impact: dict) -> str | None:
    """Ensure type conversion is applied when schema type changes."""
    old_type = impact.get("old_value")
    new_type = impact.get("new_value")
    if not old_type or not new_type:
        return None
    type_conversions = {
        ("string", "integer"): ["int(", "parseInt(", "strconv.Atoi("],
        ("integer", "string"): ["str(", "String(", "toString()", "fmt.Sprintf("],
        ("string", "number"): ["float(", "parseFloat(", "strconv.ParseFloat("],
        ("number", "string"): ["str(", "String(", "toString()"],
        ("boolean", "string"): ["str(", "String(", "toString()"],
        ("string", "boolean"): ["bool(", "parseBool(", "Boolean("],
    }
    conversions = type_conversions.get((old_type, new_type), [])
    for conv in conversions:
        if conv in content:
            return None
    return f"schema type changed from {old_type} to {new_type} but no type conversion found in patched code"


def _guard_schema_format_changed(content: str, impact: dict) -> str | None:
    """Ensure format-dependent code is updated when format changes."""
    old_format = impact.get("old_value")
    new_format = impact.get("new_value")
    if not old_format or not new_format:
        return None
    format_indicators = {
        "date-time": ["datetime", "DateTime", "Timestamp", "time.Parse"],
        "date": ["date", "Date", "time.Parse"],
        "email": ["email", "Email", "mail.ParseAddress"],
        "uri": ["url", "URL", "url.Parse"],
        "uuid": ["uuid", "UUID", "uuid.NewRandom"],
    }
    old_indicators = format_indicators.get(old_format, [])
    new_indicators = format_indicators.get(new_format, [])
    if old_indicators and new_indicators:
        has_old = any(ind in content for ind in old_indicators)
        if has_old:
            return f"format changed from {old_format} to {new_format} but old format handling still present"
    return None


def _guard_schema_property_type_changed(content: str, impact: dict) -> str | None:
    """Ensure property access code handles new type."""
    prop_name = impact.get("schema_path", "").split(".")[-1] if impact.get("schema_path") else None
    if not prop_name:
        return None
    old_type = impact.get("old_value")
    new_type = impact.get("new_value")
    if not old_type or not new_type:
        return None
    type_conversions = {
        ("string", "integer"): ["int(", "parseInt("],
        ("integer", "string"): ["str(", "toString()"],
        ("string", "number"): ["float(", "parseFloat("],
        ("number", "string"): ["str(", "toString()"],
    }
    conversions = type_conversions.get((old_type, new_type), [])
    for conv in conversions:
        if conv in content and prop_name in content:
            return None
    return None


def _guard_operation_deprecated(content: str, impact: dict) -> str | None:
    """Ensure deprecation warning or migration comment is added."""
    deprecation_indicators = ["deprecated", "DeprecationWarning", "warnings.warn", "# DEPRECATED", "# Migration"]
    for indicator in deprecation_indicators:
        if indicator.lower() in content.lower():
            return None
    return "operation was deprecated but no deprecation warning or migration comment found in patched code"


def _guard_sunset_date(content: str, impact: dict) -> str | None:
    """Ensure migration planning comment is added when sunset date is set."""
    sunset_indicators = ["sunset", "migration", "# TODO", "# FIXME", "# MIGRATE"]
    for indicator in sunset_indicators:
        if indicator.lower() in content.lower():
            return None
    return "sunset date was set but no migration planning comment found in patched code"


# ── Registry ────────────────────────────────────────────────────────────────

SEMANTIC_GUARDS: dict[str, Callable[[str, dict], str | None]] = {
    "method_changed": _guard_method_changed,
    "param_removed": _guard_param_removed,
    "param_type_changed": _guard_param_type_changed,
    "param_required": _guard_param_required,
    "enum_value_removed": _guard_enum_value_removed,
    "response_code_removed": _guard_response_code_removed,
    "response_schema_removed": _guard_response_schema_removed,
    "security_scheme_type_changed": _guard_security_scheme_type_changed,
    "schema_property_removed": _guard_schema_property_removed,
    "schema_property_type_changed": _guard_schema_property_type_changed,
    "schema_type_changed": _guard_schema_type_changed,
    "schema_format_changed": _guard_schema_format_changed,
    "required_field_added": _guard_required_field_added,
    "request_body_removed": _guard_body_removed,
    "request_body_added": _guard_request_body_added,
    "request_body_required_changed": _guard_request_body_required_changed,
    "oauth_scope_removed": _guard_oauth_scope_removed,
    "endpoint_removed": _guard_endpoint_removed,
    "http_method_removed": _guard_method_changed,
    "operation_deprecated": _guard_operation_deprecated,
    "sunset_date": _guard_sunset_date,
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
