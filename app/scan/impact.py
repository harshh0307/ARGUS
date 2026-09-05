from __future__ import annotations

from app.scan.models import (
    AnyUsage,
    AuthUsage,
    BodyUsage,
    DriftSignal,
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
    drift_signals: list[DriftSignal],
) -> list[Impact]:
    """Link code usages to drift signals that affect them."""
    impacts: list[Impact] = []

    for signal in drift_signals:
        if signal.severity not in ("breaking", "deprecation"):
            continue

        for usage in usages:
            if signal.method == usage.method and match_path(usage.path, signal.path):
                impacts.append(Impact(usage, signal))

        if signal.kind in _HEADER_DRIFT_KINDS:
            for header in headers:
                if _header_matches_signal(header, signal):
                    impacts.append(Impact(header, signal))

        if signal.kind in _BODY_DRIFT_KINDS:
            for body in bodies:
                if _body_matches_signal(body, signal):
                    impacts.append(Impact(body, signal))

        if signal.kind in _AUTH_DRIFT_KINDS:
            for auth in auths:
                if _auth_matches_signal(auth, signal):
                    impacts.append(Impact(auth, signal))

        if signal.kind in _RESPONSE_DRIFT_KINDS:
            for resp in responses:
                if _response_matches_signal(resp, signal):
                    impacts.append(Impact(resp, signal))

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


_HEADER_DRIFT_KINDS = {
    "auth_changed",
    "security_changed",
    "operation_security_changed",
    "header_removed",
    "header_added",
    "content_type_changed",
}

_BODY_DRIFT_KINDS = {
    "schema_field_removed",
    "schema_field_renamed",
    "schema_type_changed",
    "required_field_added",
    "enum_value_removed",
    "request_body_removed",
    "request_body_added",
}

_AUTH_DRIFT_KINDS = {
    "auth_changed",
    "security_changed",
    "operation_security_changed",
    "oauth_scope_removed",
}

_RESPONSE_DRIFT_KINDS = {
    "response结构调整",
    "response_code_removed",
    "schema_field_removed",
    "schema_type_changed",
}


def _header_matches_signal(header: HeaderUsage, signal: DriftSignal) -> bool:
    if signal.kind in ("auth_changed", "security_changed", "operation_security_changed"):
        return header.context in ("bearer", "api_key", "auth")
    if signal.kind == "content_type_changed":
        return header.header_name.lower() == "content-type"
    return signal.kind in ("header_removed", "header_added")


def _body_matches_signal(body: BodyUsage, signal: DriftSignal) -> bool:
    if signal.kind in ("request_body_removed", "request_body_added"):
        return True
    if signal.kind == "schema_field_removed":
        return signal.new_value in body.fields_used if signal.new_value else False
    if signal.kind == "required_field_added":
        return signal.new_value not in body.fields_used if signal.new_value else False
    return signal.kind in ("schema_type_changed", "enum_value_removed")


def _auth_matches_signal(auth: AuthUsage, signal: DriftSignal) -> bool:
    if signal.kind in ("auth_changed", "security_changed", "operation_security_changed"):
        return True
    if signal.kind == "oauth_scope_removed":
        return auth.auth_type == "oauth2"
    return False


def _response_matches_signal(resp: ResponseUsage, signal: DriftSignal) -> bool:
    if signal.kind == "response_code_removed":
        return signal.old_value in resp.status_codes_used if signal.old_value else False
    return signal.kind in ("response结构调整", "schema_type_changed", "schema_field_removed")
