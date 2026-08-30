from __future__ import annotations

from app.detection.models import ADDITIVE, BREAKING, DEPRECATION, WARNING, Change
from app.detection.normalize import normalize_spec
from app.detection.schema_diff import diff_schemas


def diff_specs(old: dict, new: dict) -> list[Change]:
    old_norm = normalize_spec(old)
    new_norm = normalize_spec(new)
    changes: list[Change] = []

    for key in old_norm:
        if key not in new_norm:
            method, path = key.split(" ", 1)
            changes.append(
                Change("endpoint_removed", BREAKING, path, method, "endpoint is no longer documented")
            )
            continue
        changes.extend(_diff_operation(key, old_norm[key], new_norm[key]))

    for key in new_norm:
        if key not in old_norm:
            method, path = key.split(" ", 1)
            changes.append(
                Change("endpoint_added", ADDITIVE, path, method, "new endpoint documented")
            )

    old_version = old.get("info", {}).get("version") if isinstance(old.get("info"), dict) else None
    new_version = new.get("info", {}).get("version") if isinstance(new.get("info"), dict) else None
    if old_version and new_version and old_version != new_version:
        changes.append(
            Change(
                "api_version_changed",
                WARNING,
                "/",
                "info",
                f"API version changed from {old_version} to {new_version}",
                old_value=old_version,
                new_value=new_version,
            )
        )

    return sorted(changes, key=lambda c: (c.path, c.method, c.kind))


def _diff_operation(key: str, old_op: dict, new_op: dict) -> list[Change]:
    method, path = key.split(" ", 1)
    changes: list[Change] = []

    if not old_op.get("deprecated") and new_op.get("deprecated"):
        changes.append(
            Change(
                "operation_deprecated",
                DEPRECATION,
                path,
                method,
                "endpoint is now deprecated",
            )
        )

    if new_op.get("sunset") and not old_op.get("sunset"):
        changes.append(
            Change(
                "sunset_date",
                WARNING,
                path,
                method,
                f"sunset date detected in {new_op['sunset']}",
            )
        )

    old_params = {p[:2]: p for p in old_op["parameters"]}
    new_params = {p[:2]: p for p in new_op["parameters"]}

    for ident, old_p in old_params.items():
        if ident not in new_params:
            changes.append(
                Change("param_removed", BREAKING, path, method, f"parameter '{ident[1]}' ({ident[0]}) removed")
            )
            continue
        new_p = new_params[ident]
        if not old_p[2] and new_p[2]:
            changes.append(
                Change("param_required", BREAKING, path, method, f"parameter '{ident[1]}' is now required")
            )
        if old_p[3] and new_p[3] and old_p[3] != new_p[3]:
            changes.append(
                Change(
                    "param_type_changed",
                    BREAKING,
                    path,
                    method,
                    f"parameter '{ident[1]}' type changed from {old_p[3]} to {new_p[3]}",
                )
            )
        if not old_p[4] and new_p[4]:
            changes.append(
                Change(
                    "param_deprecated",
                    DEPRECATION,
                    path,
                    method,
                    f"parameter '{ident[1]}' ({ident[0]}) is now deprecated",
                )
            )

    for code in sorted(old_op["responses"] - new_op["responses"]):
        changes.append(
            Change("response_code_removed", BREAKING, path, method, f"response status {code} removed")
        )

    old_body = old_op.get("requestBody")
    new_body = new_op.get("requestBody")
    if old_body or new_body:
        changes.extend(
            diff_schemas(old_body, new_body, path, method, "requestBody")
        )

    old_resp = old_op.get("responseSchemas") or {}
    new_resp = new_op.get("responseSchemas") or {}
    all_resp_keys = set(old_resp) | set(new_resp)
    for resp_key in sorted(all_resp_keys):
        old_rs = old_resp.get(resp_key)
        new_rs = new_resp.get(resp_key)
        if old_rs or new_rs:
            changes.extend(
                diff_schemas(old_rs, new_rs, path, method, f"responses.{key}")
            )

    return changes
