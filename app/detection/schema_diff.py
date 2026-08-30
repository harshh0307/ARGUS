from __future__ import annotations

from typing import Any

from app.detection.models import ADDITIVE, BREAKING, Change


def diff_schemas(
    old_schema: dict | None,
    new_schema: dict | None,
    path: str,
    method: str,
    schema_location: str,
    *,
    old_required: list[str] | None = None,
    new_required: list[str] | None = None,
) -> list[Change]:
    """Compare two OpenAPI schema objects and emit Changes for differences."""
    if old_schema is None and new_schema is None:
        return []
    if old_schema is None:
        return [
            Change(
                "response_schema_added",
                ADDITIVE,
                path,
                method,
                f"{schema_location} schema added",
                new_value=new_schema,
                schema_path=schema_location,
            )
        ]
    if new_schema is None:
        return [
            Change(
                "response_schema_removed",
                BREAKING,
                path,
                method,
                f"{schema_location} schema removed",
                old_value=old_schema,
                schema_path=schema_location,
            )
        ]

    changes: list[Change] = []

    old_type = old_schema.get("type")
    new_type = new_schema.get("type")
    if old_type and new_type and old_type != new_type:
        changes.append(
            Change(
                "schema_type_changed",
                BREAKING,
                path,
                method,
                f"{schema_location} type changed from {old_type} to {new_type}",
                old_value=old_type,
                new_value=new_type,
                schema_path=schema_location,
            )
        )

    old_props = old_schema.get("properties") or {}
    new_props = new_schema.get("properties") or {}
    old_req = set(old_required or old_schema.get("required") or [])
    new_req = set(new_required or new_schema.get("required") or [])

    for prop_name in old_req - new_req:
        changes.append(
            Change(
                "required_field_removed",
                BREAKING,
                path,
                method,
                f"{schema_location} required field '{prop_name}' is no longer required",
                old_value=prop_name,
                schema_path=f"{schema_location}.{prop_name}",
            )
        )

    for prop_name in new_req - old_req:
        if prop_name not in old_props:
            changes.append(
                Change(
                    "request_body_property_added",
                    ADDITIVE,
                    path,
                    method,
                    f"{schema_location} new required field '{prop_name}' added",
                    new_value=new_props.get(prop_name),
                    schema_path=f"{schema_location}.{prop_name}",
                )
            )
        else:
            changes.append(
                Change(
                    "required_field_added",
                    BREAKING,
                    path,
                    method,
                    f"{schema_location} field '{prop_name}' is now required",
                    old_value=old_props.get(prop_name),
                    new_value=new_props.get(prop_name),
                    schema_path=f"{schema_location}.{prop_name}",
                )
            )

    for prop_name in old_props:
        if prop_name not in new_props:
            changes.append(
                Change(
                    "request_body_property_removed",
                    BREAKING,
                    path,
                    method,
                    f"{schema_location} property '{prop_name}' removed",
                    old_value=old_props[prop_name],
                    schema_path=f"{schema_location}.{prop_name}",
                )
            )
        elif prop_name in new_props:
            prop_changes = _diff_property(
                old_props[prop_name],
                new_props[prop_name],
                path,
                method,
                f"{schema_location}.{prop_name}",
            )
            changes.extend(prop_changes)

    for prop_name in new_props:
        if prop_name not in old_props:
            changes.append(
                Change(
                    "request_body_property_added",
                    ADDITIVE,
                    path,
                    method,
                    f"{schema_location} property '{prop_name}' added",
                    new_value=new_props[prop_name],
                    schema_path=f"{schema_location}.{prop_name}",
                )
            )

    old_enum = set(old_schema.get("enum") or [])
    new_enum = set(new_schema.get("enum") or [])
    if old_enum and new_enum and old_enum != new_enum:
        removed = old_enum - new_enum
        added = new_enum - old_enum
        if removed:
            changes.append(
                Change(
                    "enum_value_removed",
                    BREAKING,
                    path,
                    method,
                    f"{schema_location} enum values removed: {sorted(removed)}",
                    old_value=sorted(removed),
                    schema_path=schema_location,
                )
            )
        if added:
            changes.append(
                Change(
                    "enum_value_added",
                    ADDITIVE,
                    path,
                    method,
                    f"{schema_location} enum values added: {sorted(added)}",
                    new_value=sorted(added),
                    schema_path=schema_location,
                )
            )

    old_format = old_schema.get("format")
    new_format = new_schema.get("format")
    if old_format and new_format and old_format != new_format:
        changes.append(
            Change(
                "schema_format_changed",
                BREAKING,
                path,
                method,
                f"{schema_location} format changed from {old_format} to {new_format}",
                old_value=old_format,
                new_value=new_format,
                schema_path=schema_location,
            )
        )

    old_items = old_schema.get("items")
    new_items = new_schema.get("items")
    if old_items and new_items:
        item_changes = diff_schemas(
            old_items, new_items, path, method,
            f"{schema_location}[]",
        )
        changes.extend(item_changes)

    return changes


def _diff_property(
    old_prop: Any,
    new_prop: Any,
    path: str,
    method: str,
    schema_path: str,
) -> list[Change]:
    if not isinstance(old_prop, dict) or not isinstance(new_prop, dict):
        return []

    changes: list[Change] = []

    old_type = old_prop.get("type")
    new_type = new_prop.get("type")
    if old_type and new_type and old_type != new_type:
        changes.append(
            Change(
                "schema_property_type_changed",
                BREAKING,
                path,
                method,
                f"{schema_path} type changed from {old_type} to {new_type}",
                old_value=old_type,
                new_value=new_type,
                schema_path=schema_path,
            )
        )

    old_format = old_prop.get("format")
    new_format = new_prop.get("format")
    if old_format and new_format and old_format != new_format:
        changes.append(
            Change(
                "schema_format_changed",
                BREAKING,
                path,
                method,
                f"{schema_path} format changed from {old_format} to {new_format}",
                old_value=old_format,
                new_value=new_format,
                schema_path=schema_path,
            )
        )

    old_enum = set(old_prop.get("enum") or [])
    new_enum = set(new_prop.get("enum") or [])
    if old_enum and new_enum and old_enum != new_enum:
        removed = old_enum - new_enum
        added = new_enum - old_enum
        if removed:
            changes.append(
                Change(
                    "enum_value_removed",
                    BREAKING,
                    path,
                    method,
                    f"{schema_path} enum values removed: {sorted(removed)}",
                    old_value=sorted(removed),
                    schema_path=schema_path,
                )
            )
        if added:
            changes.append(
                Change(
                    "enum_value_added",
                    ADDITIVE,
                    path,
                    method,
                    f"{schema_path} enum values added: {sorted(added)}",
                    new_value=sorted(added),
                    schema_path=schema_path,
                )
            )

    if old_prop.get("type") == "object" or "properties" in old_prop or "properties" in new_prop:
        nested = diff_schemas(old_prop, new_prop, path, method, schema_path)
        changes.extend(nested)

    if old_prop.get("type") == "array" or new_prop.get("type") == "array":
        old_items = old_prop.get("items")
        new_items = new_prop.get("items")
        if old_items and new_items:
            item_changes = diff_schemas(old_items, new_items, path, method, f"{schema_path}[]")
            changes.extend(item_changes)

    return changes
