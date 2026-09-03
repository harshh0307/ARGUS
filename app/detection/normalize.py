"""Enhanced OpenAPI spec normalizer.

Extracts comprehensive data from every operation for full diff coverage.
Previous version extracted 7 attributes per operation.
This version extracts 20+ attributes including parameters, headers, security, servers.
"""

from __future__ import annotations

from typing import Any

METHODS = ("get", "post", "put", "patch", "delete", "head", "options", "trace")


def normalize_spec(spec: dict) -> dict:
    """Normalize all operations in a spec into a flat dict keyed by 'method path'."""
    normalized: dict = {}
    for path, path_item in sorted(spec.get("paths", {}).items()):
        if not isinstance(path_item, dict):
            continue
        for method in METHODS:
            operation = path_item.get(method)
            if isinstance(operation, dict):
                normalized[f"{method} {path}"] = _normalize_operation(operation)
    return normalized


def _normalize_operation(operation: dict) -> dict:
    """Extract all relevant attributes from a single operation."""
    parameters = _extract_parameters(operation)
    responses = set(operation.get("responses", {}).keys())

    deprecated = bool(operation.get("deprecated", False))
    operation_id = operation.get("operationId") or None
    sunset = _extract_sunset(operation)

    request_body = operation.get("requestBody")
    request_body_schema = _extract_body_schema(request_body)
    request_body_required = (
        bool(request_body.get("required", False))
        if isinstance(request_body, dict)
        else False
    )
    request_content_types = _extract_content_types(request_body)

    response_schemas = _extract_response_schemas(operation.get("responses", {}))
    response_headers = _extract_response_headers(operation.get("responses", {}))
    response_content_types = _extract_response_content_types(
        operation.get("responses", {})
    )

    summary = operation.get("summary") or None
    description = operation.get("description") or None
    tags = list(operation.get("tags") or [])
    security = operation.get("security")
    servers = operation.get("servers")

    return {
        "parameters": parameters,
        "responses": responses,
        "deprecated": deprecated,
        "operationId": operation_id,
        "sunset": sunset,
        "requestBody": request_body_schema,
        "requestBodyRequired": request_body_required,
        "requestContentTypes": request_content_types,
        "responseSchemas": response_schemas,
        "responseHeaders": response_headers,
        "responseContentTypes": response_content_types,
        "summary": summary,
        "description": description,
        "tags": tags,
        "security": security,
        "servers": servers,
    }


def _extract_parameters(operation: dict) -> list[tuple]:
    """Extract full parameter details from an operation."""
    parameters = []
    for param in operation.get("parameters", []):
        if not isinstance(param, dict):
            continue
        name = param.get("name")
        if not name:
            continue
        loc = param.get("in", "")
        required = bool(param.get("required", False))
        schema = param.get("schema") or {}
        ptype = schema.get("type") if isinstance(schema, dict) else None
        pformat = schema.get("format") if isinstance(schema, dict) else None
        deprecated = bool(param.get("deprecated", False))
        description = param.get("description") or None
        default = schema.get("default") if isinstance(schema, dict) else None
        example = param.get("example") or (schema.get("example") if isinstance(schema, dict) else None)
        enum = schema.get("enum") if isinstance(schema, dict) else None
        style = param.get("style") or None
        explode = param.get("explode") if "explode" in param else None
        allow_empty = param.get("allowEmptyValue") if "allowEmptyValue" in param else None
        allow_reserved = param.get("allowReserved") if "allowReserved" in param else None
        parameters.append((
            loc, name, required, ptype, pformat, deprecated,
            description, default, example, enum, style, explode,
            allow_empty, allow_reserved,
        ))
    parameters.sort(key=lambda p: (p[0], p[1]))
    return parameters


def _extract_sunset(operation: dict) -> str | None:
    """Detect sunset indicator in parameters or description."""
    for header_name in ("sunset", "x-sunset"):
        for param in operation.get("parameters", []):
            if isinstance(param, dict) and param.get("name", "").lower() == header_name:
                return "header"
    desc = operation.get("description", "") or ""
    if "sunset" in desc.lower():
        return "description"
    return None


def _extract_body_schema(request_body: Any) -> dict | None:
    """Extract JSON schema from request body."""
    if not isinstance(request_body, dict):
        return None
    content = request_body.get("content")
    if not isinstance(content, dict):
        return None
    for media_type in ("application/json", "application/x-www-form-urlencoded", "multipart/form-data"):
        if media_type in content:
            return content[media_type].get("schema")
    first = next(iter(content.values()), None)
    if isinstance(first, dict):
        return first.get("schema")
    return None


def _extract_content_types(body: Any) -> list[str]:
    """Extract list of content types from a request body or response."""
    if not isinstance(body, dict):
        return []
    content = body.get("content")
    if not isinstance(content, dict):
        return []
    return sorted(content.keys())


def _extract_response_schemas(responses: dict) -> dict[str, Any]:
    """Extract schemas for each response status code."""
    schemas: dict[str, Any] = {}
    for code, resp in responses.items():
        if not isinstance(resp, dict):
            continue
        content = resp.get("content")
        if not isinstance(content, dict):
            continue
        for media_type, media_obj in content.items():
            if isinstance(media_obj, dict) and "schema" in media_obj:
                schemas[f"{code}.{media_type}"] = media_obj["schema"]
                break
    return schemas


def _extract_response_headers(responses: dict) -> dict[str, dict[str, Any]]:
    """Extract response headers per status code."""
    headers: dict[str, dict[str, Any]] = {}
    for code, resp in responses.items():
        if not isinstance(resp, dict):
            continue
        resp_headers = resp.get("headers")
        if not isinstance(resp_headers, dict):
            continue
        for name, header_obj in resp_headers.items():
            if isinstance(header_obj, dict):
                schema = header_obj.get("schema") or {}
                headers[f"{code}.{name}"] = {
                    "name": name,
                    "status_code": code,
                    "description": header_obj.get("description"),
                    "required": header_obj.get("required", False),
                    "deprecated": header_obj.get("deprecated", False),
                    "schema_type": schema.get("type") if isinstance(schema, dict) else None,
                }
    return headers


def _extract_response_content_types(responses: dict) -> dict[str, list[str]]:
    """Extract content types per response status code."""
    content_types: dict[str, list[str]] = {}
    for code, resp in responses.items():
        if not isinstance(resp, dict):
            continue
        content = resp.get("content")
        if isinstance(content, dict):
            content_types[code] = sorted(content.keys())
    return content_types


def extract_spec_metadata(spec: dict) -> dict:
    """Extract top-level spec metadata: info, servers, security, tags, webhooks, components."""
    return {
        "info": spec.get("info") or {},
        "servers": spec.get("servers") or [],
        "security": spec.get("security") or [],
        "tags": spec.get("tags") or [],
        "externalDocs": spec.get("externalDocs"),
        "webhooks": spec.get("webhooks") or {},
        "components": spec.get("components") or {},
    }
