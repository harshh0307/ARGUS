"""Deterministic strategy registry for API change fixes.

Design principle: most fixes are mechanical — regex replacement + validation.
Only when the deterministic template fails do we fall back to the LLM.

This registry maps ChangeKind values to FixStrategy instances.
Each strategy defines:
- A regex pattern to find affected code
- A replacement template (or function)
- A validator that confirms the fix is correct
- A guard that rejects patches that don't address the change
- Optional LLM fallback instructions for complex cases
"""

from __future__ import annotations

import re

from app.detection.models import ChangeKind
from app.fix.models import FixStrategy

# ── Registry ────────────────────────────────────────────────────────────────

STRATEGY_REGISTRY: dict[str, FixStrategy] = {}


def register_strategy(strategy: FixStrategy) -> None:
    """Register a deterministic fix strategy for a change kind."""
    STRATEGY_REGISTRY[strategy.kind] = strategy


def get_strategy(kind: str) -> FixStrategy | None:
    """Look up the strategy for a change kind."""
    return STRATEGY_REGISTRY.get(kind)


def needs_llm(kind: str) -> bool:
    """Return True if this change kind has no deterministic fix."""
    strategy = STRATEGY_REGISTRY.get(kind)
    if strategy is None:
        return True  # unknown kind → use LLM
    return strategy.llm_required


# ── Validators ──────────────────────────────────────────────────────────────


def _validate_method_changed(content: str, impact: dict) -> bool:
    """Check that the new method is present and old is gone."""
    old = impact.get("old_method", "")
    new = impact.get("new_method", "")
    if old and old.lower() in content.lower():
        return False  # old method still present
    return not (new and new.lower() not in content.lower())


def _validate_param_removed(content: str, impact: dict) -> bool:
    """Check that the removed parameter is no longer passed."""
    param = impact.get("param_name", "")
    if not param:
        return True
    # Check for param= in function call
    return not bool(re.search(rf"{re.escape(param)}\s*=", content))


def _validate_param_added(content: str, impact: dict) -> bool:
    """Check that a new required parameter is present."""
    param = impact.get("param_name", "")
    if not param:
        return True
    return bool(re.search(rf"{re.escape(param)}\s*=", content))


def _validate_enum_value_removed(content: str, impact: dict) -> bool:
    """Check that the old enum value is no longer used."""
    old = impact.get("old_value", "")
    if not old:
        return True
    return not bool(re.search(rf"""['"]({re.escape(old)})['"]""", content))


def _validate_type_changed(content: str, impact: dict) -> bool:
    """Check that a type conversion is present."""
    new_type = impact.get("new_type", "")
    if not new_type:
        return True
    conversions = {
        "integer": r"\bint\s*\(",
        "number": r"\b(float|int)\s*\(",
        "string": r"\bstr\s*\(",
        "boolean": r"\bbool\s*\(",
    }
    pattern = conversions.get(new_type)
    if pattern:
        return bool(re.search(pattern, content))
    return True  # unknown type, accept


def _validate_body_removed(content: str, impact: dict) -> bool:
    """Check that request body argument is no longer passed."""
    body_patterns = [
        r"json\s*=\s*\{",
        r"body\s*=\s*\{",
        r"data\s*=\s*\{",
        r"json\s*=\s*json\.dumps",
    ]
    for pattern in body_patterns:
        if re.search(pattern, content):
            return False
    return True


# ── Guards ──────────────────────────────────────────────────────────────────


def _guard_method_changed(content: str, impact: dict) -> str | None:
    """Reject if old HTTP method still called."""
    old = impact.get("old_method", "")
    if not old:
        return None
    patterns = [
        rf"\.{old}\s*\(",
        rf"""["']method["']\s*:\s*["']({old})["']""",
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
    if re.search(rf"(status|statusCode|status_code)\s*[=!]=?\s*{old}", content):
        return f"Removed status code {old} still checked"
    return None


def _guard_body_removed(content: str, impact: dict) -> str | None:
    """Reject if request body still sent."""
    body_patterns = [r"json\s*=\s*\{", r"body\s*=\s*\{", r"data\s*=\s*\{"]
    for pattern in body_patterns:
        if re.search(pattern, content):
            return "Request body still present in patched code"
    return None


# ── Register strategies ─────────────────────────────────────────────────────

# Endpoint changes
register_strategy(
    FixStrategy(
        kind=ChangeKind.METHOD_CHANGED,
        description="Change HTTP method (e.g. PUT → PATCH)",
        pattern=r"\.(put|post|patch|delete|get|head|options)\s*\(",
        replacement_template=None,  # use function for dynamic replacement
        validator=_validate_method_changed,
        guard=_guard_method_changed,
        llm_required=False,
        examples=[
            {"before": "requests.put(url, json=data)", "after": "requests.patch(url, json=data)"},
            {"before": "client.post(url)", "after": "client.put(url)"},
        ],
    )
)

register_strategy(
    FixStrategy(
        kind=ChangeKind.ENDPOINT_REMOVED,
        description="Endpoint no longer exists — remove or rewrite call",
        llm_required=True,
        prompt_instructions=(
            "This endpoint has been removed. If a replacement exists, "
            "rewrite the call to use it. Otherwise, remove the call and "
            "add appropriate error handling or a comment."
        ),
    )
)

register_strategy(
    FixStrategy(
        kind=ChangeKind.ENDPOINT_ADDED,
        description="New endpoint added (no fix needed for existing code)",
        llm_required=False,
    )
)

# Parameter changes
register_strategy(
    FixStrategy(
        kind=ChangeKind.PARAM_REMOVED,
        description="Parameter removed from endpoint",
        validator=_validate_param_removed,
        guard=_guard_param_removed,
        llm_required=False,
        examples=[
            {"before": "requests.get(url, params={'q': val, 'old': x})", "after": "requests.get(url, params={'q': val})"},
        ],
    )
)

register_strategy(
    FixStrategy(
        kind=ChangeKind.PARAM_REQUIRED,
        description="Parameter became required — add with default/example value",
        pattern=r"(params|query|headers)\s*=\s*\{([^}]*)\}",
        replacement_template=None,  # use function for dynamic replacement
        validator=_validate_param_added,
        guard=None,
        llm_required=False,
        prompt_instructions=(
            "This parameter is now required. Add it to the function call "
            "with an appropriate default value or example from the spec."
        ),
        examples=[
            {"before": "requests.get(url, params={'q': val})", "after": "requests.get(url, params={'q': val, 'per_page': 30})"},
            {"before": "client.get(url)", "after": "client.get(url, params={'required_param': 'default'})"},
        ],
    )
)

register_strategy(
    FixStrategy(
        kind=ChangeKind.PARAM_TYPE_CHANGED,
        description="Parameter type changed (e.g. string → integer)",
        validator=_validate_type_changed,
        llm_required=False,
        examples=[
            {"before": "params={'id': str(user_id)}", "after": "params={'id': int(user_id)}"},
        ],
    )
)

register_strategy(
    FixStrategy(
        kind=ChangeKind.PARAM_ADDED,
        description="New optional parameter added (no fix needed)",
        llm_required=False,
    )
)

# Enum changes
register_strategy(
    FixStrategy(
        kind=ChangeKind.ENUM_VALUE_REMOVED,
        description="Enum value no longer valid",
        pattern=r"""['"](\w+)['"]""",
        replacement_template=None,  # use function for dynamic replacement
        validator=_validate_enum_value_removed,
        guard=_guard_enum_value_removed,
        llm_required=False,
        prompt_instructions=(
            "This enum value is no longer valid. Replace it with the "
            "closest valid alternative from the new enum values."
        ),
        examples=[
            {"before": "status = 'closed'", "after": "status = 'completed'"},
            {"before": "type = 'bug'", "after": "type = 'issue'"},
        ],
    )
)

register_strategy(
    FixStrategy(
        kind=ChangeKind.ENUM_VALUE_ADDED,
        description="New enum value added (no fix needed)",
        llm_required=False,
    )
)

# Request body changes
register_strategy(
    FixStrategy(
        kind=ChangeKind.REQUEST_BODY_REMOVED,
        description="Request body no longer accepted",
        validator=_validate_body_removed,
        guard=_guard_body_removed,
        llm_required=False,
        examples=[
            {"before": "requests.post(url, json=payload)", "after": "requests.post(url)"},
        ],
    )
)

register_strategy(
    FixStrategy(
        kind=ChangeKind.REQUEST_BODY_ADDED,
        description="Request body now required",
        pattern=r"\.(get|post|put|patch|delete)\s*\([^)]*\)",
        replacement_template=None,  # use function for dynamic replacement
        llm_required=False,
        prompt_instructions=(
            "This endpoint now requires a request body. Add the body "
            "argument with the correct structure from the new spec."
        ),
        examples=[
            {"before": "requests.post(url)", "after": "requests.post(url, json={'field': 'value'})"},
            {"before": "client.put(url)", "after": "client.put(url, json=payload)"},
        ],
    )
)

register_strategy(
    FixStrategy(
        kind=ChangeKind.REQUEST_BODY_REQUIRED_CHANGED,
        description="Request body required flag changed",
        pattern=r"\.(get|post|put|patch|delete)\s*\([^)]*\)",
        replacement_template=None,  # use function for dynamic replacement
        llm_required=False,
        prompt_instructions=(
            "The request body required status changed. Update the call "
            "to add or remove the body argument as appropriate."
        ),
        examples=[
            {"before": "requests.post(url, json=data)", "after": "requests.post(url)"},
            {"before": "requests.post(url)", "after": "requests.post(url, json=data)"},
        ],
    )
)

# Response changes
register_strategy(
    FixStrategy(
        kind=ChangeKind.RESPONSE_CODE_REMOVED,
        description="Response status code no longer returned",
        validator=lambda c, i: not re.search(
            rf"(status|statusCode|status_code)\s*[=!]=?\s*{i.get('old_value', '')}",
            c,
        ),
        guard=_guard_response_code_removed,
        llm_required=False,
    )
)

register_strategy(
    FixStrategy(
        kind=ChangeKind.RESPONSE_CODE_ADDED,
        description="New response status code (no fix needed)",
        llm_required=False,
    )
)

register_strategy(
    FixStrategy(
        kind=ChangeKind.RESPONSE_SCHEMA_REMOVED,
        description="Response schema removed",
        pattern=r"""(response|resp|res)\[['"](\w+)['"]\]""",
        replacement_template=None,  # use function for dynamic replacement
        llm_required=False,
        prompt_instructions=(
            "The response schema for this status code has been removed. "
            "Update error handling or remove the response handling block."
        ),
        examples=[
            {"before": "data = response['removed_field']", "after": "data = response.get('available_field')"},
            {"before": "user = resp.json()['nested']", "after": "user = resp.json()"},
        ],
    )
)

# Schema changes
register_strategy(
    FixStrategy(
        kind=ChangeKind.SCHEMA_TYPE_CHANGED,
        description="Schema type changed (e.g. string → integer)",
        pattern=r"(\w+)\s*(?:=\s*|:\s*)(\w+)",
        replacement_template=None,  # use function for dynamic replacement
        validator=_validate_type_changed,
        llm_required=False,
        prompt_instructions=(
            "The schema type changed. Add type conversion or update "
            "the code to handle the new type correctly."
        ),
        examples=[
            {"before": "user_id = response['id']", "after": "user_id = int(response['id'])"},
            {"before": "count = data['total']", "after": "count = str(data['total'])"},
        ],
    )
)

register_strategy(
    FixStrategy(
        kind=ChangeKind.SCHEMA_FORMAT_CHANGED,
        description="Schema format changed (e.g. int32 → int64)",
        pattern=r"(datetime|date|uuid|uri|email|timestamp)",
        replacement_template=None,  # use function for dynamic replacement
        llm_required=False,
        prompt_instructions=(
            "The schema format changed. Update code that depends on "
            "the specific format (e.g. date format, integer size)."
        ),
        examples=[
            {"before": "datetime.strptime(val, '%Y-%m-%d')", "after": "datetime.fromisoformat(val)"},
            {"before": "uuid.UUID(val)", "after": "val"},  # if format changed from uuid to string
        ],
    )
)

register_strategy(
    FixStrategy(
        kind=ChangeKind.SCHEMA_PROPERTY_TYPE_CHANGED,
        description="Schema property type changed",
        pattern=r"(\w+)\s*(?:=\s*|:\s*)(\w+)",
        replacement_template=None,  # use function for dynamic replacement
        validator=_validate_type_changed,
        llm_required=False,
        prompt_instructions=(
            "A property's type changed. Update code that accesses "
            "or constructs this property to use the new type."
        ),
        examples=[
            {"before": "data['count'] = response['total']", "after": "data['count'] = int(response['total'])"},
            {"before": "item['name'] = obj['title']", "after": "item['name'] = str(obj['title'])"},
        ],
    )
)

register_strategy(
    FixStrategy(
        kind=ChangeKind.SCHEMA_PROPERTY_REMOVED,
        description="Schema property removed",
        pattern=r"""\[['"](\w+)['"]\]|\.(\w+)""",
        replacement_template=None,  # use function for dynamic replacement
        llm_required=False,
        prompt_instructions=(
            "A property has been removed from the schema. Remove any "
            "code that accesses this property."
        ),
        examples=[
            {"before": "data = response['deprecated_field']", "after": "data = response.get('new_field')"},
            {"before": "obj.old_prop", "after": "obj.new_prop"},
        ],
    )
)

register_strategy(
    FixStrategy(
        kind=ChangeKind.SCHEMA_PROPERTY_ADDED,
        description="New schema property (no fix needed)",
        llm_required=False,
    )
)

register_strategy(
    FixStrategy(
        kind=ChangeKind.REQUIRED_FIELD_ADDED,
        description="Field became required",
        pattern=r"\{([^}]*)\}",
        replacement_template=None,  # use function for dynamic replacement
        llm_required=False,
        prompt_instructions=(
            "A field has become required. Ensure the code provides "
            "this field when constructing the request body."
        ),
        examples=[
            {"before": "payload = {'name': name}", "after": "payload = {'name': name, 'email': email}"},
            {"before": "data = {'title': title}", "after": "data = {'title': title, 'body': body}"},
        ],
    )
)

register_strategy(
    FixStrategy(
        kind=ChangeKind.REQUIRED_FIELD_REMOVED,
        description="Field no longer required (no fix needed)",
        llm_required=False,
    )
)

# Security changes
register_strategy(
    FixStrategy(
        kind=ChangeKind.SECURITY_SCHEME_TYPE_CHANGED,
        description="Authentication type changed",
        pattern=r"(Bearer|API[_-]?Key|OAuth2|Basic)",
        replacement_template=None,  # use function for dynamic replacement
        llm_required=False,
        prompt_instructions=(
            "The authentication type changed (e.g. from Bearer to API key). "
            "Update the authentication code to match the new scheme."
        ),
        examples=[
            {"before": "headers['Authorization'] = f'Bearer {token}'", "after": "headers['X-Api-Key'] = api_key"},
            {"before": "headers['Authorization'] = f'Bearer {token}'", "after": "headers['Authorization'] = f'Basic {b64}'"},
        ],
    )
)

register_strategy(
    FixStrategy(
        kind=ChangeKind.OAUTH_SCOPE_REMOVED,
        description="OAuth scope no longer available",
        pattern=r"""(scope|scopes)\s*=\s*['"][^'"]+['"]""",
        replacement_template=None,  # use function for dynamic replacement
        llm_required=False,
        prompt_instructions=(
            "An OAuth scope has been removed. Update the authorization "
            "request to remove this scope."
        ),
        examples=[
            {"before": "scopes = ['read', 'write', 'admin']", "after": "scopes = ['read', 'write']"},
            {"before": "scope='user:read user:write'", "after": "scope='user:read'"},
        ],
    )
)

# Deprecation
register_strategy(
    FixStrategy(
        kind=ChangeKind.OPERATION_DEPRECATED,
        description="Endpoint deprecated",
        pattern=r"(requests|httpx|client)\.\w+\s*\(",
        replacement_template=None,  # use function for dynamic replacement
        llm_required=False,
        prompt_instructions=(
            "This endpoint is deprecated. If a replacement exists, "
            "migrate to it. Otherwise, add a deprecation warning comment."
        ),
        examples=[
            {"before": "requests.get(url)", "after": "# DEPRECATED: Use new_endpoint instead\nrequests.get(url)"},
            {"before": "client.post(url)", "after": "# TODO: Migrate to new_endpoint\nclient.post(url)"},
        ],
    )
)

register_strategy(
    FixStrategy(
        kind=ChangeKind.SUNSET_DATE,
        description="Sunset date set — endpoint will be removed",
        pattern=r"(requests|httpx|client)\.\w+\s*\(",
        replacement_template=None,  # use function for dynamic replacement
        llm_required=False,
        prompt_instructions=(
            "This endpoint has a sunset date. Plan migration to the "
            "replacement endpoint before the sunset date."
        ),
        examples=[
            {"before": "requests.get(url)", "after": "# SUNSET: Migrate before 2025-01-01\nrequests.get(url)"},
            {"before": "client.post(url)", "after": "# TODO: Migrate before sunset\nclient.post(url)"},
        ],
    )
)

# Informational (no fix needed)
for kind_str in [
    ChangeKind.API_VERSION_CHANGED,
    ChangeKind.INFO_TITLE_CHANGED,
    ChangeKind.INFO_DESCRIPTION_CHANGED,
    ChangeKind.INFO_CONTACT_CHANGED,
    ChangeKind.INFO_LICENSE_CHANGED,
    ChangeKind.INFO_TERMS_OF_SERVICE_CHANGED,
    ChangeKind.OPENAPI_VERSION_CHANGED,
    ChangeKind.EXTERNAL_DOCS_CHANGED,
    ChangeKind.OPERATION_SUMMARY_CHANGED,
    ChangeKind.OPERATION_DESCRIPTION_CHANGED,
    ChangeKind.OPERATION_TAGS_CHANGED,
    ChangeKind.TAG_ADDED,
    ChangeKind.TAG_REMOVED,
    ChangeKind.TAG_DESCRIPTION_CHANGED,
    ChangeKind.SCHEMA_DESCRIPTION_CHANGED,
    ChangeKind.SCHEMA_TITLE_CHANGED,
    ChangeKind.RESPONSE_DESCRIPTION_CHANGED,
    ChangeKind.SERVER_DESCRIPTION_CHANGED,
    ChangeKind.OPERATION_ID_ADDED,
    ChangeKind.OPERATION_ID_REMOVED,
    ChangeKind.OPERATION_ID_CHANGED,
]:
    register_strategy(
        FixStrategy(kind=kind_str, description="Informational change", llm_required=False)
    )

# Schema constraints (informational — no code fix needed)
for kind_str in [
    ChangeKind.SCHEMA_MIN_CHANGED,
    ChangeKind.SCHEMA_MAX_CHANGED,
    ChangeKind.SCHEMA_EXCLUSIVE_MIN_CHANGED,
    ChangeKind.SCHEMA_EXCLUSIVE_MAX_CHANGED,
    ChangeKind.SCHEMA_MIN_LENGTH_CHANGED,
    ChangeKind.SCHEMA_MAX_LENGTH_CHANGED,
    ChangeKind.SCHEMA_PATTERN_CHANGED,
    ChangeKind.SCHEMA_MIN_ITEMS_CHANGED,
    ChangeKind.SCHEMA_MAX_ITEMS_CHANGED,
    ChangeKind.SCHEMA_UNIQUE_ITEMS_CHANGED,
    ChangeKind.SCHEMA_MIN_PROPERTIES_CHANGED,
    ChangeKind.SCHEMA_MAX_PROPERTIES_CHANGED,
    ChangeKind.SCHEMA_MULTIPLE_OF_CHANGED,
    ChangeKind.SCHEMA_NULLABLE_CHANGED,
    ChangeKind.SCHEMA_READ_ONLY_CHANGED,
    ChangeKind.SCHEMA_WRITE_ONLY_CHANGED,
    ChangeKind.SCHEMA_DEFAULT_CHANGED,
    ChangeKind.SCHEMA_DEPRECATED_CHANGED,
    ChangeKind.SCHEMA_EXAMPLE_CHANGED,
    ChangeKind.SCHEMA_EXAMPLES_CHANGED,
    ChangeKind.ADDITIONAL_PROPERTIES_CHANGED,
    ChangeKind.SCHEMA_DISCRIMINATOR_CHANGED,
    ChangeKind.SCHEMA_CONTENT_MEDIA_TYPE_CHANGED,
    ChangeKind.SCHEMA_CONTENT_ENCODING_CHANGED,
    ChangeKind.SCHEMA_IF_THEN_ELSE_CHANGED,
]:
    register_strategy(
        FixStrategy(kind=kind_str, description="Schema constraint change", llm_required=False)
    )

# Schema composition (mostly informational)
for kind_str in [
    ChangeKind.SCHEMA_ALLOF_ADDED,
    ChangeKind.SCHEMA_ALLOF_REMOVED,
    ChangeKind.SCHEMA_ALLOF_SCHEMA_CHANGED,
    ChangeKind.SCHEMA_ONEOF_ADDED,
    ChangeKind.SCHEMA_ONEOF_REMOVED,
    ChangeKind.SCHEMA_ONEOF_SCHEMA_CHANGED,
    ChangeKind.SCHEMA_ANYOF_ADDED,
    ChangeKind.SCHEMA_ANYOF_REMOVED,
    ChangeKind.SCHEMA_ANYOF_SCHEMA_CHANGED,
    ChangeKind.SCHEMA_NOT_CHANGED,
    ChangeKind.SCHEMA_PREFIX_ITEMS_CHANGED,
    ChangeKind.SCHEMA_CONTAINS_CHANGED,
]:
    register_strategy(
        FixStrategy(kind=kind_str, description="Schema composition change", llm_required=False)
    )

# Servers (informational for code — infrastructure change)
for kind_str in [
    ChangeKind.SERVER_ADDED,
    ChangeKind.SERVER_REMOVED,
    ChangeKind.SERVER_URL_CHANGED,
    ChangeKind.SERVER_DESCRIPTION_CHANGED,
    ChangeKind.SERVER_VARIABLE_ADDED,
    ChangeKind.SERVER_VARIABLE_REMOVED,
    ChangeKind.SERVER_VARIABLE_DEFAULT_CHANGED,
    ChangeKind.SERVER_VARIABLE_ENUM_CHANGED,
]:
    register_strategy(
        FixStrategy(kind=kind_str, description="Server configuration change", llm_required=False)
    )

# Components (informational — shared definitions)
for kind_str in [
    ChangeKind.COMPONENT_SCHEMA_CHANGED,
    ChangeKind.COMPONENT_PARAMETER_CHANGED,
    ChangeKind.COMPONENT_RESPONSE_CHANGED,
    ChangeKind.COMPONENT_REQUEST_BODY_CHANGED,
    ChangeKind.COMPONENT_HEADER_CHANGED,
    ChangeKind.COMPONENT_SECURITY_SCHEME_CHANGED,
]:
    register_strategy(
        FixStrategy(kind=kind_str, description="Component definition change", llm_required=False)
    )

# Webhooks (informational)
for kind_str in [
    ChangeKind.WEBHOOK_ADDED,
    ChangeKind.WEBHOOK_REMOVED,
    ChangeKind.WEBHOOK_METHOD_ADDED,
    ChangeKind.WEBHOOK_METHOD_REMOVED,
    ChangeKind.WEBHOOK_OPERATION_CHANGED,
    ChangeKind.WEBHOOK_SCHEMA_CHANGED,
]:
    register_strategy(
        FixStrategy(kind=kind_str, description="Webhook change", llm_required=False)
    )

# Remaining parameter changes (informational)
for kind_str in [
    ChangeKind.PARAM_OPTIONAL,
    ChangeKind.PARAM_FORMAT_CHANGED,
    ChangeKind.PARAM_LOCATION_CHANGED,
    ChangeKind.PARAM_DEPRECATED,
    ChangeKind.PARAM_UNDEPRECATED,
    ChangeKind.PARAM_DESCRIPTION_CHANGED,
    ChangeKind.PARAM_STYLE_CHANGED,
    ChangeKind.PARAM_EXPLODE_CHANGED,
    ChangeKind.PARAM_ALLOW_EMPTY_VALUE_CHANGED,
    ChangeKind.PARAM_DEFAULT_CHANGED,
    ChangeKind.PARAM_EXAMPLE_CHANGED,
    ChangeKind.PARAM_ENUM_CHANGED,
]:
    register_strategy(
        FixStrategy(kind=kind_str, description="Parameter metadata change", llm_required=False)
    )

# Remaining operation changes
for kind_str in [
    ChangeKind.OPERATION_UNDEPRECATED,
    ChangeKind.OPERATION_SECURITY_ADDED,
    ChangeKind.OPERATION_SECURITY_REMOVED,
    ChangeKind.OPERATION_SECURITY_CHANGED,
    ChangeKind.CONTENT_TYPE_CHANGED,
]:
    register_strategy(
        FixStrategy(kind=kind_str, description="Operation metadata change", llm_required=False)
    )

# Remaining request body changes
for kind_str in [
    ChangeKind.REQUEST_CONTENT_TYPE_ADDED,
    ChangeKind.REQUEST_CONTENT_TYPE_REMOVED,
    ChangeKind.REQUEST_BODY_SCHEMA_CHANGED,
]:
    register_strategy(
        FixStrategy(kind=kind_str, description="Request body metadata change", llm_required=False)
    )

# Remaining response changes
for kind_str in [
    ChangeKind.RESPONSE_CONTENT_TYPE_ADDED,
    ChangeKind.RESPONSE_CONTENT_TYPE_REMOVED,
    ChangeKind.RESPONSE_SCHEMA_CHANGED,
    ChangeKind.RESPONSE_SCHEMA_ADDED,
    ChangeKind.RESPONSE_HEADER_ADDED,
    ChangeKind.RESPONSE_HEADER_REMOVED,
    ChangeKind.RESPONSE_HEADER_CHANGED,
    ChangeKind.RESPONSE_LINK_CHANGED,
]:
    register_strategy(
        FixStrategy(kind=kind_str, description="Response metadata change", llm_required=False)
    )

# Remaining security changes
for kind_str in [
    ChangeKind.GLOBAL_SECURITY_ADDED,
    ChangeKind.GLOBAL_SECURITY_REMOVED,
    ChangeKind.GLOBAL_SECURITY_CHANGED,
    ChangeKind.SECURITY_SCHEME_ADDED,
    ChangeKind.SECURITY_SCHEME_REMOVED,
    ChangeKind.SECURITY_SCHEME_NAME_CHANGED,
    ChangeKind.SECURITY_SCHEME_IN_CHANGED,
    ChangeKind.OAUTH_SCOPE_ADDED,
    ChangeKind.OAUTH_FLOW_CHANGED,
    ChangeKind.OAUTH_URL_CHANGED,
]:
    register_strategy(
        FixStrategy(kind=kind_str, description="Security configuration change", llm_required=False)
    )

# Refs (informational)
for kind_str in [
    ChangeKind.REF_TARGET_CHANGED,
    ChangeKind.REF_BECAME_INLINE,
    ChangeKind.REF_BECAME_REFERENCE,
]:
    register_strategy(
        FixStrategy(kind=kind_str, description="$ref change", llm_required=False)
    )

# HTTP method add/remove on existing path
register_strategy(
    FixStrategy(
        kind=ChangeKind.HTTP_METHOD_ADDED,
        description="New HTTP method on existing path (additive)",
        llm_required=False,
    )
)
register_strategy(
    FixStrategy(
        kind=ChangeKind.HTTP_METHOD_REMOVED,
        description="HTTP method removed from path",
        pattern=r"\.(get|post|put|patch|delete|head|options)\s*\(",
        replacement_template=None,  # use function for dynamic replacement
        guard=_guard_method_changed,
        llm_required=False,
        prompt_instructions=(
            "An HTTP method has been removed from this path. "
            "Update or remove any code that uses this method."
        ),
        examples=[
            {"before": "requests.delete(url)", "after": "requests.post(url, json={'action': 'archive'})"},
            {"before": "client.put(url)", "after": "client.patch(url)"},
        ],
    )
)
