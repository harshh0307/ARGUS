from __future__ import annotations

from app.detection.models import ADDITIVE, BREAKING, Change
from app.detection.normalize import normalize_spec


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

    return sorted(changes, key=lambda c: (c.path, c.method, c.kind))


def _diff_operation(key: str, old_op: dict, new_op: dict) -> list[Change]:
    method, path = key.split(" ", 1)
    changes: list[Change] = []

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

    for code in sorted(old_op["responses"] - new_op["responses"]):
        changes.append(
            Change("response_code_removed", BREAKING, path, method, f"response status {code} removed")
        )

    return changes
