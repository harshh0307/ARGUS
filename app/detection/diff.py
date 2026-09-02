"""Enhanced OpenAPI diff engine.

Detects all change kinds across endpoints, operations, parameters,
request bodies, responses, servers, security, info, tags, components,
webhooks, and external docs.
"""

from __future__ import annotations

from typing import Any

from app.detection.models import (
    ADDITIVE,
    BREAKING,
    DEPRECATION,
    WARNING,
    Change,
    ChangeKind,
)
from app.detection.normalize import extract_spec_metadata, normalize_spec
from app.detection.schema_diff import diff_schemas


def diff_specs(old: dict, new: dict) -> list[Change]:
    """Diff two OpenAPI specs and return all detected changes."""
    old_norm = normalize_spec(old)
    new_norm = normalize_spec(new)
    changes: list[Change] = []

    # ── Method change detection (operationId cross-reference) ───────────
    changes.extend(_diff_method_changes(old_norm, new_norm))

    # ── Endpoint add/remove ────────────────────────────────────────────
    for key in old_norm:
        if key not in new_norm:
            method, path = key.split(" ", 1)
            changes.append(
                Change(ChangeKind.ENDPOINT_REMOVED, BREAKING, path, method, "endpoint is no longer documented")
            )
            continue
        changes.extend(_diff_operation(key, old_norm[key], new_norm[key]))

    for key in new_norm:
        if key not in old_norm:
            method, path = key.split(" ", 1)
            changes.append(
                Change(ChangeKind.ENDPOINT_ADDED, ADDITIVE, path, method, "new endpoint documented")
            )

    # ── Top-level spec changes ─────────────────────────────────────────
    old_meta = extract_spec_metadata(old)
    new_meta = extract_spec_metadata(new)
    changes.extend(_diff_info(old_meta["info"], new_meta["info"]))
    changes.extend(_diff_servers(old_meta["servers"], new_meta["servers"]))
    changes.extend(_diff_security_global(old_meta["security"], new_meta["security"]))
    changes.extend(_diff_tags(old_meta["tags"], new_meta["tags"]))
    changes.extend(_diff_webhooks(old_meta["webhooks"], new_meta["webhooks"]))
    changes.extend(_diff_components(old_meta["components"], new_meta["components"]))
    changes.extend(_diff_external_docs(old_meta["externalDocs"], new_meta["externalDocs"]))

    return sorted(changes, key=lambda c: (c.path, c.method, c.kind.value))


# ── Method change detection ─────────────────────────────────────────────────


def _diff_method_changes(old_norm: dict, new_norm: dict) -> list[Change]:
    """Detect PUT→PATCH style method changes via operationId cross-reference."""
    changes: list[Change] = []

    # Build operationId → (method, path) maps
    old_by_id: dict[str, tuple[str, str]] = {}
    for key, op in old_norm.items():
        oid = op.get("operationId")
        if oid:
            method, path = key.split(" ", 1)
            old_by_id[oid] = (method, path)

    new_by_id: dict[str, tuple[str, str]] = {}
    for key, op in new_norm.items():
        oid = op.get("operationId")
        if oid:
            method, path = key.split(" ", 1)
            new_by_id[oid] = (method, path)

    # Cross-reference: same operationId but different method
    for oid, (old_method, old_path) in old_by_id.items():
        if oid in new_by_id:
            new_method, new_path = new_by_id[oid]
            if old_method != new_method and old_path == new_path:
                changes.append(
                    Change(
                        ChangeKind.METHOD_CHANGED,
                        BREAKING,
                        old_path,
                        new_method,
                        f"HTTP method changed from {old_method.upper()} to {new_method.upper()}",
                        old_method=old_method,
                        new_method=new_method,
                    )
                )

    return changes


# ── Operation-level diff ────────────────────────────────────────────────────


def _diff_operation(key: str, old_op: dict, new_op: dict) -> list[Change]:
    """Diff all attributes of a single operation."""
    method, path = key.split(" ", 1)
    changes: list[Change] = []

    # Deprecation
    changes.extend(_diff_deprecation(old_op, new_op, path, method))

    # Operation metadata
    changes.extend(_diff_operation_metadata(old_op, new_op, path, method))

    # Parameters
    changes.extend(_diff_parameters(old_op.get("parameters", []), new_op.get("parameters", []), path, method))

    # Request body
    changes.extend(_diff_request_body(old_op, new_op, path, method))

    # Responses
    changes.extend(_diff_responses(old_op, new_op, path, method))

    return changes


def _diff_deprecation(old_op: dict, new_op: dict, path: str, method: str) -> list[Change]:
    """Detect deprecation and sunset changes."""
    changes: list[Change] = []

    if not old_op.get("deprecated") and new_op.get("deprecated"):
        changes.append(
            Change(ChangeKind.OPERATION_DEPRECATED, DEPRECATION, path, method, "endpoint is now deprecated")
        )
    elif old_op.get("deprecated") and not new_op.get("deprecated"):
        changes.append(
            Change(ChangeKind.OPERATION_UNDEPRECATED, WARNING, path, method, "deprecated flag removed")
        )

    if new_op.get("sunset") and not old_op.get("sunset"):
        changes.append(
            Change(ChangeKind.SUNSET_DATE, WARNING, path, method, f"sunset date detected in {new_op['sunset']}")
        )

    return changes


def _diff_operation_metadata(old_op: dict, new_op: dict, path: str, method: str) -> list[Change]:
    """Detect operationId, summary, description, tags, security changes."""
    changes: list[Change] = []

    # operationId
    old_oid = old_op.get("operationId")
    new_oid = new_op.get("operationId")
    if old_oid and not new_oid:
        changes.append(
            Change(ChangeKind.OPERATION_ID_REMOVED, WARNING, path, method, f"operationId '{old_oid}' removed")
        )
    elif not old_oid and new_oid:
        changes.append(
            Change(ChangeKind.OPERATION_ID_ADDED, ADDITIVE, path, method, f"operationId '{new_oid}' added")
        )
    elif old_oid and new_oid and old_oid != new_oid:
        changes.append(
            Change(
                ChangeKind.OPERATION_ID_CHANGED, BREAKING, path, method,
                f"operationId changed from '{old_oid}' to '{new_oid}'",
                old_value=old_oid, new_value=new_oid,
            )
        )

    # Summary
    old_s = old_op.get("summary")
    new_s = new_op.get("summary")
    if old_s != new_s and (old_s or new_s):
        changes.append(
            Change(ChangeKind.OPERATION_SUMMARY_CHANGED, WARNING, path, method, "operation summary changed")
        )

    # Description
    old_d = old_op.get("description")
    new_d = new_op.get("description")
    if old_d != new_d and (old_d or new_d):
        changes.append(
            Change(ChangeKind.OPERATION_DESCRIPTION_CHANGED, WARNING, path, method, "operation description changed")
        )

    # Tags
    old_tags = set(old_op.get("tags") or [])
    new_tags = set(new_op.get("tags") or [])
    if old_tags != new_tags:
        changes.append(
            Change(ChangeKind.OPERATION_TAGS_CHANGED, WARNING, path, method, "operation tags changed")
        )

    # Security
    old_sec = old_op.get("security")
    new_sec = new_op.get("security")
    if old_sec != new_sec:
        if not old_sec and new_sec:
            changes.append(
                Change(ChangeKind.OPERATION_SECURITY_ADDED, WARNING, path, method, "security requirement added")
            )
        elif old_sec and not new_sec:
            changes.append(
                Change(ChangeKind.OPERATION_SECURITY_REMOVED, WARNING, path, method, "security requirement removed")
            )
        else:
            changes.append(
                Change(ChangeKind.OPERATION_SECURITY_CHANGED, BREAKING, path, method, "security requirement changed")
            )

    return changes


def _diff_parameters(old_params: list, new_params: list, path: str, method: str) -> list[Change]:
    """Diff all parameter attributes between old and new operations."""
    changes: list[Change] = []

    # Index by (location, name)
    old_by_ident = {p[:2]: p for p in old_params}
    new_by_ident = {p[:2]: p for p in new_params}

    # Removed parameters
    for ident, old_p in old_by_ident.items():
        if ident not in new_by_ident:
            changes.append(
                Change(ChangeKind.PARAM_REMOVED, BREAKING, path, method, f"parameter '{ident[1]}' ({ident[0]}) removed")
            )
            continue
        new_p = new_by_ident[ident]
        changes.extend(_diff_single_param(old_p, new_p, path, method))

    # Added parameters
    for ident, new_p in new_by_ident.items():
        if ident not in old_by_ident:
            changes.append(
                Change(ChangeKind.PARAM_ADDED, ADDITIVE, path, method, f"parameter '{ident[1]}' ({ident[0]}) added")
            )

    return changes


def _diff_single_param(old_p: tuple, new_p: tuple, path: str, method: str) -> list[Change]:
    """Diff attributes of a single parameter (old_p and new_p are tuples)."""
    changes: list[Change] = []
    loc, name = old_p[0], old_p[1]
    ident_str = f"parameter '{name}' ({loc})"

    # Required
    if not old_p[2] and new_p[2]:
        changes.append(Change(ChangeKind.PARAM_REQUIRED, BREAKING, path, method, f"{ident_str} is now required"))
    elif old_p[2] and not new_p[2]:
        changes.append(Change(ChangeKind.PARAM_OPTIONAL, ADDITIVE, path, method, f"{ident_str} is now optional"))

    # Type
    if old_p[3] and new_p[3] and old_p[3] != new_p[3]:
        changes.append(
            Change(ChangeKind.PARAM_TYPE_CHANGED, BREAKING, path, method, f"{ident_str} type changed from {old_p[3]} to {new_p[3]}", old_value=old_p[3], new_value=new_p[3])
        )

    # Format
    if old_p[4] and new_p[4] and old_p[4] != new_p[4]:
        changes.append(
            Change(ChangeKind.PARAM_FORMAT_CHANGED, BREAKING, path, method, f"{ident_str} format changed from {old_p[4]} to {new_p[4]}", old_value=old_p[4], new_value=new_p[4])
        )

    # Deprecated
    if not old_p[5] and new_p[5]:
        changes.append(Change(ChangeKind.PARAM_DEPRECATED, DEPRECATION, path, method, f"{ident_str} is now deprecated"))
    elif old_p[5] and not new_p[5]:
        changes.append(Change(ChangeKind.PARAM_UNDEPRECATED, WARNING, path, method, f"{ident_str} deprecated flag removed"))

    # Description (index 6)
    if old_p[6] != new_p[6] and (old_p[6] or new_p[6]):
        changes.append(Change(ChangeKind.PARAM_DESCRIPTION_CHANGED, WARNING, path, method, f"{ident_str} description changed"))

    # Default (index 7)
    if old_p[7] != new_p[7] and (old_p[7] is not None or new_p[7] is not None):
        changes.append(Change(ChangeKind.PARAM_DEFAULT_CHANGED, WARNING, path, method, f"{ident_str} default value changed", old_value=old_p[7], new_value=new_p[7]))

    # Example (index 8)
    if old_p[8] != new_p[8] and (old_p[8] is not None or new_p[8] is not None):
        changes.append(Change(ChangeKind.PARAM_EXAMPLE_CHANGED, WARNING, path, method, f"{ident_str} example changed"))

    # Enum (index 9)
    old_enum = set(old_p[9] or [])
    new_enum = set(new_p[9] or [])
    if old_enum != new_enum and (old_enum or new_enum):
        changes.append(Change(ChangeKind.PARAM_ENUM_CHANGED, BREAKING, path, method, f"{ident_str} enum values changed", old_value=sorted(old_enum), new_value=sorted(new_enum)))

    # Style (index 10)
    if old_p[10] != new_p[10] and (old_p[10] or new_p[10]):
        changes.append(Change(ChangeKind.PARAM_STYLE_CHANGED, BREAKING, path, method, f"{ident_str} style changed"))

    # Explode (index 11)
    if old_p[11] != new_p[11] and (old_p[11] is not None or new_p[11] is not None):
        changes.append(Change(ChangeKind.PARAM_EXPLODE_CHANGED, BREAKING, path, method, f"{ident_str} explode changed"))

    # AllowEmptyValue (index 12)
    if old_p[12] != new_p[12] and (old_p[12] is not None or new_p[12] is not None):
        changes.append(Change(ChangeKind.PARAM_ALLOW_EMPTY_VALUE_CHANGED, BREAKING, path, method, f"{ident_str} allowEmptyValue changed"))

    return changes


# ── Request body diff ───────────────────────────────────────────────────────


def _diff_request_body(old_op: dict, new_op: dict, path: str, method: str) -> list[Change]:
    """Diff request body: required flag, content types, schema."""
    changes: list[Change] = []
    old_body = old_op.get("requestBody")
    new_body = new_op.get("requestBody")

    old_has_body = old_body is not None
    new_has_body = new_body is not None

    if not old_has_body and new_has_body:
        changes.append(Change(ChangeKind.REQUEST_BODY_ADDED, BREAKING, path, method, "request body now required"))
    elif old_has_body and not new_has_body:
        changes.append(Change(ChangeKind.REQUEST_BODY_REMOVED, WARNING, path, method, "request body removed"))
    elif old_has_body and new_has_body:
        # Required flag
        old_req = old_op.get("requestBodyRequired", False)
        new_req = new_op.get("requestBodyRequired", False)
        if old_req != new_req:
            changes.append(Change(ChangeKind.REQUEST_BODY_REQUIRED_CHANGED, BREAKING, path, method, f"request body required changed from {old_req} to {new_req}"))

        # Content types
        old_ct = set(old_op.get("requestContentTypes", []))
        new_ct = set(new_op.get("requestContentTypes", []))
        for ct in old_ct - new_ct:
            changes.append(Change(ChangeKind.REQUEST_CONTENT_TYPE_REMOVED, BREAKING, path, method, f"request content type '{ct}' removed"))
        for ct in new_ct - old_ct:
            changes.append(Change(ChangeKind.REQUEST_CONTENT_TYPE_ADDED, ADDITIVE, path, method, f"request content type '{ct}' added"))

        # Schema
        old_schema = old_body
        new_schema = new_body
        if old_schema or new_schema:
            changes.extend(diff_schemas(old_schema, new_schema, path, method, "requestBody"))

    return changes


# ── Response diff ───────────────────────────────────────────────────────────


def _diff_responses(old_op: dict, new_op: dict, path: str, method: str) -> list[Change]:
    """Diff responses: status codes, schemas, headers, content types."""
    changes: list[Change] = []

    old_codes = old_op.get("responses", set())
    new_codes = new_op.get("responses", set())

    # Removed response codes
    for code in sorted(old_codes - new_codes):
        changes.append(Change(ChangeKind.RESPONSE_CODE_REMOVED, BREAKING, path, method, f"response status {code} removed"))

    # Added response codes
    for code in sorted(new_codes - old_codes):
        changes.append(Change(ChangeKind.RESPONSE_CODE_ADDED, ADDITIVE, path, method, f"response status {code} added"))

    # Response schema diff
    old_resp = old_op.get("responseSchemas") or {}
    new_resp = new_op.get("responseSchemas") or {}
    all_resp_keys = set(old_resp) | set(new_resp)
    for resp_key in sorted(all_resp_keys):
        old_rs = old_resp.get(resp_key)
        new_rs = new_resp.get(resp_key)
        code = resp_key.split(".")[0]
        if old_rs is None and new_rs is not None:
            changes.append(Change(ChangeKind.RESPONSE_SCHEMA_ADDED, ADDITIVE, path, method, f"response schema added for {code}"))
        elif old_rs is not None and new_rs is None:
            changes.append(Change(ChangeKind.RESPONSE_SCHEMA_REMOVED, BREAKING, path, method, f"response schema removed for {code}"))
        elif old_rs or new_rs:
            changes.extend(diff_schemas(old_rs, new_rs, path, method, f"responses.{code}"))

    # Response header diff
    old_headers = old_op.get("responseHeaders") or {}
    new_headers = new_op.get("responseHeaders") or {}
    all_hk = set(old_headers) | set(new_headers)
    for hk in sorted(all_hk):
        oh = old_headers.get(hk)
        nh = new_headers.get(hk)
        if oh and not nh:
            changes.append(Change(ChangeKind.RESPONSE_HEADER_REMOVED, BREAKING, path, method, f"response header '{hk.split('.')[-1]}' removed for {hk.split('.')[0]}"))
        elif not oh and nh:
            changes.append(Change(ChangeKind.RESPONSE_HEADER_ADDED, ADDITIVE, path, method, f"response header '{hk.split('.')[-1]}' added for {hk.split('.')[0]}"))
        elif oh != nh:
            changes.append(Change(ChangeKind.RESPONSE_HEADER_CHANGED, BREAKING, path, method, f"response header '{hk.split('.')[-1]}' changed for {hk.split('.')[0]}"))

    # Response content type diff
    old_rct = old_op.get("responseContentTypes") or {}
    new_rct = new_op.get("responseContentTypes") or {}
    for code in set(old_rct) | set(new_rct):
        old_types = set(old_rct.get(code, []))
        new_types = set(new_rct.get(code, []))
        for ct in old_types - new_types:
            changes.append(Change(ChangeKind.RESPONSE_CONTENT_TYPE_REMOVED, BREAKING, path, method, f"response content type '{ct}' removed for {code}"))
        for ct in new_types - old_types:
            changes.append(Change(ChangeKind.RESPONSE_CONTENT_TYPE_ADDED, ADDITIVE, path, method, f"response content type '{ct}' added for {code}"))

    return changes


# ── Top-level diffs ─────────────────────────────────────────────────────────


def _diff_info(old_info: dict, new_info: dict) -> list[Change]:
    """Diff info object: title, version, description, contact, license, TOS."""
    changes: list[Change] = []

    old_ver = old_info.get("version")
    new_ver = new_info.get("version")
    if old_ver and new_ver and old_ver != new_ver:
        changes.append(Change(ChangeKind.API_VERSION_CHANGED, WARNING, "/", "info", f"API version changed from {old_ver} to {new_ver}", old_value=old_ver, new_value=new_ver))

    old_title = old_info.get("title")
    new_title = new_info.get("title")
    if old_title != new_title and (old_title or new_title):
        changes.append(Change(ChangeKind.INFO_TITLE_CHANGED, WARNING, "/", "info", "API title changed"))

    old_desc = old_info.get("description")
    new_desc = new_info.get("description")
    if old_desc != new_desc and (old_desc or new_desc):
        changes.append(Change(ChangeKind.INFO_DESCRIPTION_CHANGED, WARNING, "/", "info", "API description changed"))

    old_contact = old_info.get("contact")
    new_contact = new_info.get("contact")
    if old_contact != new_contact:
        changes.append(Change(ChangeKind.INFO_CONTACT_CHANGED, WARNING, "/", "info", "contact info changed"))

    old_license = old_info.get("license")
    new_license = new_info.get("license")
    if old_license != new_license:
        changes.append(Change(ChangeKind.INFO_LICENSE_CHANGED, WARNING, "/", "info", "license changed"))

    old_tos = old_info.get("termsOfService")
    new_tos = new_info.get("termsOfService")
    if old_tos != new_tos and (old_tos or new_tos):
        changes.append(Change(ChangeKind.INFO_TERMS_OF_SERVICE_CHANGED, WARNING, "/", "info", "terms of service changed"))

    return changes


def _diff_servers(old_servers: list, new_servers: list) -> list[Change]:
    """Diff server entries: URL, description, variables."""
    changes: list[Change] = []

    old_urls = {s.get("url"): s for s in old_servers if isinstance(s, dict)}
    new_urls = {s.get("url"): s for s in new_servers if isinstance(s, dict)}

    for url, old_s in old_urls.items():
        if url not in new_urls:
            changes.append(Change(ChangeKind.SERVER_REMOVED, WARNING, "/", "info", f"server '{url}' removed"))
        else:
            new_s = new_urls[url]
            old_desc = old_s.get("description")
            new_desc = new_s.get("description")
            if old_desc != new_desc:
                changes.append(Change(ChangeKind.SERVER_DESCRIPTION_CHANGED, WARNING, "/", "info", f"server '{url}' description changed"))

            old_vars = old_s.get("variables") or {}
            new_vars = new_s.get("variables") or {}
            changes.extend(_diff_server_variables(old_vars, new_vars, url))

    for url in new_urls:
        if url not in old_urls:
            changes.append(Change(ChangeKind.SERVER_ADDED, ADDITIVE, "/", "info", f"server '{url}' added"))

    return changes


def _diff_server_variables(old_vars: dict, new_vars: dict, server_url: str) -> list[Change]:
    """Diff server variables."""
    changes: list[Change] = []

    for name, old_v in old_vars.items():
        if name not in new_vars:
            changes.append(Change(ChangeKind.SERVER_VARIABLE_REMOVED, BREAKING, "/", "info", f"server variable '{name}' removed from {server_url}"))
        elif isinstance(old_v, dict) and isinstance(new_vars.get(name), dict):
            new_v = new_vars[name]
            if old_v.get("default") != new_v.get("default"):
                changes.append(Change(ChangeKind.SERVER_VARIABLE_DEFAULT_CHANGED, BREAKING, "/", "info", f"server variable '{name}' default changed in {server_url}", old_value=old_v.get("default"), new_value=new_v.get("default")))
            old_enum = set(old_v.get("enum") or [])
            new_enum = set(new_v.get("enum") or [])
            if old_enum != new_enum:
                changes.append(Change(ChangeKind.SERVER_VARIABLE_ENUM_CHANGED, BREAKING, "/", "info", f"server variable '{name}' enum changed in {server_url}"))

    for name in new_vars:
        if name not in old_vars:
            changes.append(Change(ChangeKind.SERVER_VARIABLE_ADDED, ADDITIVE, "/", "info", f"server variable '{name}' added to {server_url}"))

    return changes


def _diff_security_global(old_sec: list, new_sec: list) -> list[Change]:
    """Diff global security requirements."""
    changes: list[Change] = []
    if old_sec != new_sec:
        if not old_sec and new_sec:
            changes.append(Change(ChangeKind.GLOBAL_SECURITY_ADDED, WARNING, "/", "info", "global security requirement added"))
        elif old_sec and not new_sec:
            changes.append(Change(ChangeKind.GLOBAL_SECURITY_REMOVED, WARNING, "/", "info", "global security requirement removed"))
        else:
            changes.append(Change(ChangeKind.GLOBAL_SECURITY_CHANGED, WARNING, "/", "info", "global security requirement changed"))
    return changes


def _diff_tags(old_tags: list, new_tags: list) -> list[Change]:
    """Diff top-level tags."""
    changes: list[Change] = []
    old_names = {t.get("name"): t for t in old_tags if isinstance(t, dict)}
    new_names = {t.get("name"): t for t in new_tags if isinstance(t, dict)}

    for name, old_tag in old_names.items():
        if name not in new_names:
            changes.append(Change(ChangeKind.TAG_REMOVED, WARNING, "/", "info", f"tag '{name}' removed"))
        elif old_tag.get("description") != new_names.get(name, {}).get("description"):
            changes.append(Change(ChangeKind.TAG_DESCRIPTION_CHANGED, WARNING, "/", "info", f"tag '{name}' description changed"))

    for name in new_names:
        if name not in old_names:
            changes.append(Change(ChangeKind.TAG_ADDED, ADDITIVE, "/", "info", f"tag '{name}' added"))

    return changes


def _diff_webhooks(old_hooks: dict, new_hooks: dict) -> list[Change]:
    """Diff webhook definitions."""
    changes: list[Change] = []

    for name in old_hooks:
        if name not in new_hooks:
            changes.append(Change(ChangeKind.WEBHOOK_REMOVED, WARNING, f"/webhooks/{name}", "info", f"webhook '{name}' removed"))

    for name in new_hooks:
        if name not in old_hooks:
            changes.append(Change(ChangeKind.WEBHOOK_ADDED, ADDITIVE, f"/webhooks/{name}", "info", f"webhook '{name}' added"))

    return changes


def _diff_components(old_comp: dict, new_comp: dict) -> list[Change]:
    """Diff component definitions (schemas, parameters, responses, etc.)."""
    changes: list[Change] = []
    component_kinds = [
        ("schemas", ChangeKind.COMPONENT_SCHEMA_CHANGED),
        ("parameters", ChangeKind.COMPONENT_PARAMETER_CHANGED),
        ("responses", ChangeKind.COMPONENT_RESPONSE_CHANGED),
        ("requestBodies", ChangeKind.COMPONENT_REQUEST_BODY_CHANGED),
        ("headers", ChangeKind.COMPONENT_HEADER_CHANGED),
        ("securitySchemes", ChangeKind.COMPONENT_SECURITY_SCHEME_CHANGED),
    ]

    for section, kind in component_kinds:
        old_items = old_comp.get(section) or {}
        new_items = new_comp.get(section) or {}
        for name in set(old_items) | set(new_items):
            if name in old_items and name in new_items:
                if old_items[name] != new_items[name]:
                    changes.append(Change(kind, WARNING, "/components", section, f"component '{name}' in {section} changed"))
            elif name in old_items and name not in new_items:
                changes.append(Change(kind, WARNING, "/components", section, f"component '{name}' in {section} removed"))
            elif name not in old_items and name in new_items:
                changes.append(Change(kind, ADDITIVE, "/components", section, f"component '{name}' in {section} added"))

    return changes


def _diff_external_docs(old_docs: Any, new_docs: Any) -> list[Change]:
    """Diff external documentation."""
    changes: list[Change] = []
    if old_docs != new_docs and (old_docs or new_docs):
        changes.append(Change(ChangeKind.EXTERNAL_DOCS_CHANGED, WARNING, "/", "info", "external documentation changed"))
    return changes
