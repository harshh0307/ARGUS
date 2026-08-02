from __future__ import annotations

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
        parameters.append((loc, name, required, ptype))
    parameters.sort(key=lambda p: (p[0], p[1]))
    responses = set(operation.get("responses", {}).keys())
    return {"parameters": parameters, "responses": responses}
