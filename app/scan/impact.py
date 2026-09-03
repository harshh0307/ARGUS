from __future__ import annotations

from app.detection.models import (
    BREAKING,
    DEPRECATION,
    Change,
    ChangeKind,
)
from app.scan.models import (
    AnyUsage,
    AuthUsage,
    BodyUsage,
    HeaderUsage,
    Impact,
    ResponseUsage,
)


def assess_impact(
    usages: list[AnyUsage],
    headers: list[HeaderUsage],
    bodies: list[BodyUsage],
    auths: list[AuthUsage],
    responses: list[ResponseUsage],
    changes: list[Change],
) -> list[Impact]:
    """Link code usages to spec changes that affect them.

    Uses all usage types for precise impact assessment:
    - Usage: basic HTTP call sites
    - HeaderUsage: header assignments (auth, content-type, etc.)
    - BodyUsage: request body field access
    - AuthUsage: authentication patterns
    - ResponseUsage: response consumption patterns
    """
    impacts: list[Impact] = []

    for change in changes:
        if change.severity not in (BREAKING, DEPRECATION):
            continue

        # Match Usage (basic call sites)
        for usage in usages:
            if change.method == usage.method and match_path(usage.path, change.path):
                impacts.append(Impact(usage, change))

        # Match HeaderUsage for header-related changes
        if change.kind in _HEADER_CHANGE_KINDS:
            for header in headers:
                if _header_matches_change(header, change):
                    impacts.append(Impact(header, change))

        # Match BodyUsage for body-related changes
        if change.kind in _BODY_CHANGE_KINDS:
            for body in bodies:
                if _body_matches_change(body, change):
                    impacts.append(Impact(body, change))

        # Match AuthUsage for auth-related changes
        if change.kind in _AUTH_CHANGE_KINDS:
            for auth in auths:
                if _auth_matches_change(auth, change):
                    impacts.append(Impact(auth, change))

        # Match ResponseUsage for response-related changes
        if change.kind in _RESPONSE_CHANGE_KINDS:
            for resp in responses:
                if _response_matches_change(resp, change):
                    impacts.append(Impact(resp, change))

    return sorted(impacts, key=lambda i: (i.usage.file, i.usage.line, i.change.kind))


def match_path(code_path: str, spec_path: str) -> bool:
    code_segments = [s for s in code_path.split("/") if s]
    spec_segments = [s for s in spec_path.split("/") if s]
    if len(code_segments) != len(spec_segments):
        return False
    for code_seg, spec_seg in zip(code_segments, spec_segments):
        if spec_seg.startswith("{") and spec_seg.endswith("}"):
            continue
        if code_seg.startswith("{") and code_seg.endswith("}"):
            if spec_seg.startswith("{") and spec_seg.endswith("}"):
                continue
            return False
        if code_seg != spec_seg:
            return False
    return True


# ── Change kind sets for each usage type ────────────────────────────────────

_HEADER_CHANGE_KINDS = {
    ChangeKind.RESPONSE_HEADER_ADDED,
    ChangeKind.RESPONSE_HEADER_REMOVED,
    ChangeKind.RESPONSE_HEADER_CHANGED,
    ChangeKind.OPERATION_SECURITY_CHANGED,
    ChangeKind.OPERATION_SECURITY_ADDED,
    ChangeKind.OPERATION_SECURITY_REMOVED,
    ChangeKind.SECURITY_SCHEME_TYPE_CHANGED,
    ChangeKind.SECURITY_SCHEME_NAME_CHANGED,
    ChangeKind.SECURITY_SCHEME_IN_CHANGED,
    ChangeKind.SECURITY_SCHEME_ADDED,
    ChangeKind.SECURITY_SCHEME_REMOVED,
    ChangeKind.OAUTH_SCOPE_ADDED,
    ChangeKind.OAUTH_SCOPE_REMOVED,
    ChangeKind.OAUTH_FLOW_CHANGED,
    ChangeKind.OAUTH_URL_CHANGED,
    ChangeKind.GLOBAL_SECURITY_ADDED,
    ChangeKind.GLOBAL_SECURITY_REMOVED,
    ChangeKind.GLOBAL_SECURITY_CHANGED,
    ChangeKind.CONTENT_TYPE_CHANGED,
    ChangeKind.REQUEST_CONTENT_TYPE_ADDED,
    ChangeKind.REQUEST_CONTENT_TYPE_REMOVED,
    ChangeKind.RESPONSE_CONTENT_TYPE_ADDED,
    ChangeKind.RESPONSE_CONTENT_TYPE_REMOVED,
}

_BODY_CHANGE_KINDS = {
    ChangeKind.REQUEST_BODY_ADDED,
    ChangeKind.REQUEST_BODY_REMOVED,
    ChangeKind.REQUEST_BODY_REQUIRED_CHANGED,
    ChangeKind.REQUEST_BODY_SCHEMA_CHANGED,
    ChangeKind.REQUEST_CONTENT_TYPE_ADDED,
    ChangeKind.REQUEST_CONTENT_TYPE_REMOVED,
    ChangeKind.SCHEMA_PROPERTY_REMOVED,
    ChangeKind.SCHEMA_PROPERTY_TYPE_CHANGED,
    ChangeKind.REQUIRED_FIELD_ADDED,
    ChangeKind.REQUIRED_FIELD_REMOVED,
    ChangeKind.ENUM_VALUE_REMOVED,
    ChangeKind.ENUM_VALUE_ADDED,
    ChangeKind.SCHEMA_TYPE_CHANGED,
    ChangeKind.SCHEMA_FORMAT_CHANGED,
    ChangeKind.SCHEMA_NULLABLE_CHANGED,
    ChangeKind.SCHEMA_DEFAULT_CHANGED,
    ChangeKind.SCHEMA_PATTERN_CHANGED,
    ChangeKind.SCHEMA_MIN_CHANGED,
    ChangeKind.SCHEMA_MAX_CHANGED,
    ChangeKind.SCHEMA_MIN_LENGTH_CHANGED,
    ChangeKind.SCHEMA_MAX_LENGTH_CHANGED,
    ChangeKind.SCHEMA_MIN_ITEMS_CHANGED,
    ChangeKind.SCHEMA_MAX_ITEMS_CHANGED,
    ChangeKind.ADDITIONAL_PROPERTIES_CHANGED,
}

_AUTH_CHANGE_KINDS = {
    ChangeKind.OPERATION_SECURITY_CHANGED,
    ChangeKind.OPERATION_SECURITY_ADDED,
    ChangeKind.OPERATION_SECURITY_REMOVED,
    ChangeKind.SECURITY_SCHEME_TYPE_CHANGED,
    ChangeKind.SECURITY_SCHEME_NAME_CHANGED,
    ChangeKind.SECURITY_SCHEME_IN_CHANGED,
    ChangeKind.SECURITY_SCHEME_ADDED,
    ChangeKind.SECURITY_SCHEME_REMOVED,
    ChangeKind.OAUTH_SCOPE_ADDED,
    ChangeKind.OAUTH_SCOPE_REMOVED,
    ChangeKind.OAUTH_FLOW_CHANGED,
    ChangeKind.OAUTH_URL_CHANGED,
    ChangeKind.GLOBAL_SECURITY_ADDED,
    ChangeKind.GLOBAL_SECURITY_REMOVED,
    ChangeKind.GLOBAL_SECURITY_CHANGED,
    ChangeKind.PARAM_REMOVED,
    ChangeKind.PARAM_TYPE_CHANGED,
    ChangeKind.PARAM_ENUM_CHANGED,
}

_RESPONSE_CHANGE_KINDS = {
    ChangeKind.RESPONSE_CODE_REMOVED,
    ChangeKind.RESPONSE_CODE_ADDED,
    ChangeKind.RESPONSE_DESCRIPTION_CHANGED,
    ChangeKind.RESPONSE_SCHEMA_REMOVED,
    ChangeKind.RESPONSE_SCHEMA_ADDED,
    ChangeKind.RESPONSE_SCHEMA_CHANGED,
    ChangeKind.RESPONSE_HEADER_REMOVED,
    ChangeKind.RESPONSE_HEADER_ADDED,
    ChangeKind.RESPONSE_HEADER_CHANGED,
    ChangeKind.RESPONSE_CONTENT_TYPE_REMOVED,
    ChangeKind.RESPONSE_CONTENT_TYPE_ADDED,
    ChangeKind.SCHEMA_PROPERTY_REMOVED,
    ChangeKind.SCHEMA_PROPERTY_TYPE_CHANGED,
    ChangeKind.SCHEMA_TYPE_CHANGED,
    ChangeKind.REQUIRED_FIELD_ADDED,
    ChangeKind.ENUM_VALUE_REMOVED,
    ChangeKind.ADDITIONAL_PROPERTIES_CHANGED,
}


# ── Matching helpers ────────────────────────────────────────────────────────

def _header_matches_change(header: HeaderUsage, change: Change) -> bool:
    """Check if a header usage is affected by a change."""
    if change.kind in {ChangeKind.OPERATION_SECURITY_CHANGED, ChangeKind.OPERATION_SECURITY_ADDED, ChangeKind.OPERATION_SECURITY_REMOVED}:
        return header.context in ("bearer", "api_key", "auth")
    if change.kind in {ChangeKind.SECURITY_SCHEME_TYPE_CHANGED, ChangeKind.SECURITY_SCHEME_NAME_CHANGED, ChangeKind.SECURITY_SCHEME_IN_CHANGED}:
        return header.context in ("bearer", "api_key", "auth")
    if change.kind in {ChangeKind.OAUTH_SCOPE_ADDED, ChangeKind.OAUTH_SCOPE_REMOVED, ChangeKind.OAUTH_FLOW_CHANGED, ChangeKind.OAUTH_URL_CHANGED}:
        return header.context == "bearer"
    if change.kind in {ChangeKind.CONTENT_TYPE_CHANGED, ChangeKind.REQUEST_CONTENT_TYPE_ADDED, ChangeKind.REQUEST_CONTENT_TYPE_REMOVED}:
        return header.header_name.lower() == "content-type"
    if change.kind in {ChangeKind.RESPONSE_CONTENT_TYPE_ADDED, ChangeKind.RESPONSE_CONTENT_TYPE_REMOVED}:
        return header.header_name.lower() in ("content-type", "accept")
    return change.kind in {ChangeKind.RESPONSE_HEADER_ADDED, ChangeKind.RESPONSE_HEADER_REMOVED, ChangeKind.RESPONSE_HEADER_CHANGED}


def _body_matches_change(body: BodyUsage, change: Change) -> bool:
    """Check if a body usage is affected by a change."""
    if change.kind in {ChangeKind.REQUEST_BODY_REMOVED, ChangeKind.REQUEST_BODY_ADDED, ChangeKind.REQUEST_BODY_REQUIRED_CHANGED}:
        return True
    if change.kind == ChangeKind.REQUEST_BODY_SCHEMA_CHANGED:
        return True
    if change.kind in {ChangeKind.SCHEMA_PROPERTY_REMOVED, ChangeKind.SCHEMA_PROPERTY_TYPE_CHANGED}:
        return change.new_value in body.fields_used if change.new_value else False
    if change.kind == ChangeKind.REQUIRED_FIELD_ADDED:
        return change.new_value not in body.fields_used if change.new_value else False
    if change.kind == ChangeKind.REQUIRED_FIELD_REMOVED:
        return True  # Field was required, now optional
    if change.kind in {ChangeKind.ENUM_VALUE_REMOVED, ChangeKind.ENUM_VALUE_ADDED}:
        return True  # Enum changes affect all users
    return change.kind in {ChangeKind.SCHEMA_TYPE_CHANGED, ChangeKind.SCHEMA_FORMAT_CHANGED}


def _auth_matches_change(auth: AuthUsage, change: Change) -> bool:
    """Check if an auth usage is affected by a change."""
    if change.kind in {ChangeKind.OPERATION_SECURITY_CHANGED, ChangeKind.OPERATION_SECURITY_ADDED, ChangeKind.OPERATION_SECURITY_REMOVED}:
        return True
    if change.kind in {ChangeKind.SECURITY_SCHEME_TYPE_CHANGED, ChangeKind.SECURITY_SCHEME_NAME_CHANGED, ChangeKind.SECURITY_SCHEME_IN_CHANGED}:
        return True
    if change.kind in {ChangeKind.OAUTH_SCOPE_ADDED, ChangeKind.OAUTH_SCOPE_REMOVED, ChangeKind.OAUTH_FLOW_CHANGED, ChangeKind.OAUTH_URL_CHANGED}:
        return auth.auth_type == "oauth2"
    if change.kind in {ChangeKind.GLOBAL_SECURITY_ADDED, ChangeKind.GLOBAL_SECURITY_REMOVED, ChangeKind.GLOBAL_SECURITY_CHANGED}:
        return True
    if change.kind in {ChangeKind.PARAM_REMOVED, ChangeKind.PARAM_TYPE_CHANGED, ChangeKind.PARAM_ENUM_CHANGED}:
        return auth.param_name is not None and change.path in ("", "/")
    return False


def _response_matches_change(resp: ResponseUsage, change: Change) -> bool:
    """Check if a response usage is affected by a change."""
    if change.kind == ChangeKind.RESPONSE_CODE_REMOVED:
        return change.old_value in resp.status_codes_used if change.old_value else False
    if change.kind == ChangeKind.RESPONSE_CODE_ADDED:
        return True  # New code could affect future handling
    if change.kind in {ChangeKind.RESPONSE_SCHEMA_REMOVED, ChangeKind.RESPONSE_SCHEMA_ADDED, ChangeKind.RESPONSE_SCHEMA_CHANGED}:
        return True
    if change.kind in {ChangeKind.RESPONSE_HEADER_REMOVED, ChangeKind.RESPONSE_HEADER_ADDED, ChangeKind.RESPONSE_HEADER_CHANGED}:
        return True
    if change.kind in {ChangeKind.RESPONSE_CONTENT_TYPE_REMOVED, ChangeKind.RESPONSE_CONTENT_TYPE_ADDED}:
        return True
    if change.kind in {ChangeKind.SCHEMA_PROPERTY_REMOVED, ChangeKind.SCHEMA_PROPERTY_TYPE_CHANGED}:
        return change.new_value in resp.fields_used if change.new_value else False
    if change.kind == ChangeKind.REQUIRED_FIELD_ADDED:
        return change.new_value not in resp.fields_used if change.new_value else False
    return False
