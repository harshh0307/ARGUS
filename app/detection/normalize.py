from __future__ import annotations

from typing import Any

METHODS = ("get", "post", "put", "patch", "delete", "head", "options", "trace")


def normalize_spec(spec: dict) -> dict:
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
        deprecated = bool(param.get("deprecated", False))
        parameters.append((loc, name, required, ptype, deprecated))
    parameters.sort(key=lambda p: (p[0], p[1]))

    responses = set(operation.get("responses", {}).keys())

    deprecated = bool(operation.get("deprecated", False))
    operation_id = operation.get("operationId") or None
    sunset = _extract_sunset(operation)

    request_body_schema = _extract_body_schema(operation.get("requestBody"))
    response_schemas = _extract_response_schemas(operation.get("responses", {}))

    return {
        "parameters": parameters,
        "responses": responses,
        "deprecated": deprecated,
        "operationId": operation_id,
        "sunset": sunset,
        "requestBody": request_body_schema,
        "responseSchemas": response_schemas,
    }


def _extract_sunset(operation: dict) -> str | None:
    for header_name in ("sunset", "x-sunset"):
        for param in operation.get("parameters", []):
            if isinstance(param, dict) and param.get("name", "").lower() == header_name:
                return "header"
    desc = operation.get("description", "") or ""
    if "sunset" in desc.lower():
        return "description"
    return None


def _extract_body_schema(request_body: Any) -> dict | None:
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


def _extract_response_schemas(responses: dict) -> dict[str, Any]:
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
