"""Enhanced schema diff engine.

Detects all schema-level changes: types, properties, required fields,
enums, formats, constraints (min/max/pattern), and composition (allOf/oneOf/anyOf).
"""

from __future__ import annotations

from typing import Any

from app.detection.models import ADDITIVE, BREAKING, WARNING, Change, ChangeKind


def diff_schemas(
    old_schema: dict | None,
    new_schema: dict | None,
    path: str,
    method: str,
    schema_location: str,
    *,
    old_required: list[str] | None = None,
    new_required: list[str] | None = None,
    depth: int = 0,
    max_depth: int = 32,
) -> list[Change]:
    """Compare two OpenAPI schema objects and emit Changes for differences."""
    if depth > max_depth:
        return []
    if old_schema is None and new_schema is None:
        return []
    if old_schema is None:
        return [Change(ChangeKind.RESPONSE_SCHEMA_ADDED, ADDITIVE, path, method, f"{schema_location} schema added", new_value=new_schema, schema_path=schema_location)]
    if new_schema is None:
        return [Change(ChangeKind.RESPONSE_SCHEMA_REMOVED, BREAKING, path, method, f"{schema_location} schema removed", old_value=old_schema, schema_path=schema_location)]

    changes: list[Change] = []

    # Type
    changes.extend(_diff_type(old_schema, new_schema, path, method, schema_location))

    # Required fields
    changes.extend(_diff_required(old_schema, new_schema, old_required, new_required, path, method, schema_location))

    # Properties
    changes.extend(_diff_properties(old_schema, new_schema, path, method, schema_location, depth, max_depth))

    # Enum
    changes.extend(_diff_enum(old_schema, new_schema, path, method, schema_location))

    # Format
    changes.extend(_diff_format(old_schema, new_schema, path, method, schema_location))

    # Constraints
    changes.extend(_diff_constraints(old_schema, new_schema, path, method, schema_location))

    # Composition
    changes.extend(_diff_composition(old_schema, new_schema, path, method, schema_location, depth, max_depth))

    # Items (arrays)
    old_items = old_schema.get("items")
    new_items = new_schema.get("items")
    if old_items or new_items:
        changes.extend(diff_schemas(old_items, new_items, path, method, f"{schema_location}[]", depth=depth + 1, max_depth=max_depth))

    # Metadata
    changes.extend(_diff_metadata(old_schema, new_schema, path, method, schema_location))

    return changes


# ── Type diff ───────────────────────────────────────────────────────────────


def _diff_type(old: dict, new: dict, path: str, method: str, loc: str) -> list[Change]:
    changes: list[Change] = []
    old_type = old.get("type")
    new_type = new.get("type")
    if old_type and new_type and old_type != new_type:
        changes.append(Change(ChangeKind.SCHEMA_TYPE_CHANGED, BREAKING, path, method, f"{loc} type changed from {old_type} to {new_type}", old_value=old_type, new_value=new_type, schema_path=loc))
    return changes


def _diff_format(old: dict, new: dict, path: str, method: str, loc: str) -> list[Change]:
    changes: list[Change] = []
    old_format = old.get("format")
    new_format = new.get("format")
    if old_format and new_format and old_format != new_format:
        changes.append(Change(ChangeKind.SCHEMA_FORMAT_CHANGED, BREAKING, path, method, f"{loc} format changed from {old_format} to {new_format}", old_value=old_format, new_value=new_format, schema_path=loc))
    return changes


# ── Required fields diff ────────────────────────────────────────────────────


def _diff_required(old_schema: dict, new_schema: dict, old_required: list[str] | None, new_required: list[str] | None, path: str, method: str, loc: str) -> list[Change]:
    changes: list[Change] = []
    old_req = set(old_required or old_schema.get("required") or [])
    new_req = set(new_required or new_schema.get("required") or [])

    for prop_name in sorted(old_req - new_req):
        changes.append(Change(ChangeKind.REQUIRED_FIELD_REMOVED, BREAKING, path, method, f"{loc} required field '{prop_name}' is no longer required", old_value=prop_name, schema_path=f"{loc}.{prop_name}"))

    old_props = old_schema.get("properties") or {}
    new_props = new_schema.get("properties") or {}
    for prop_name in sorted(new_req - old_req):
        if prop_name not in old_props:
            changes.append(Change(ChangeKind.REQUEST_BODY_PROPERTY_ADDED, ADDITIVE, path, method, f"{loc} new required field '{prop_name}' added", new_value=new_props.get(prop_name), schema_path=f"{loc}.{prop_name}"))
        else:
            changes.append(Change(ChangeKind.REQUIRED_FIELD_ADDED, BREAKING, path, method, f"{loc} field '{prop_name}' is now required", old_value=old_props.get(prop_name), new_value=new_props.get(prop_name), schema_path=f"{loc}.{prop_name}"))

    return changes


# ── Properties diff ─────────────────────────────────────────────────────────


def _diff_properties(old_schema: dict, new_schema: dict, path: str, method: str, loc: str, depth: int, max_depth: int) -> list[Change]:
    changes: list[Change] = []
    old_props = old_schema.get("properties") or {}
    new_props = new_schema.get("properties") or {}

    for prop_name in sorted(old_props):
        if prop_name not in new_props:
            changes.append(Change(ChangeKind.SCHEMA_PROPERTY_REMOVED, BREAKING, path, method, f"{loc} property '{prop_name}' removed", old_value=old_props[prop_name], schema_path=f"{loc}.{prop_name}"))
        elif prop_name in new_props:
            changes.extend(_diff_property(old_props[prop_name], new_props[prop_name], path, method, f"{loc}.{prop_name}", depth, max_depth))

    for prop_name in sorted(new_props):
        if prop_name not in old_props:
            changes.append(Change(ChangeKind.SCHEMA_PROPERTY_ADDED, ADDITIVE, path, method, f"{loc} property '{prop_name}' added", new_value=new_props[prop_name], schema_path=f"{loc}.{prop_name}"))

    return changes


def _diff_property(old_prop: Any, new_prop: Any, path: str, method: str, schema_path: str, depth: int, max_depth: int) -> list[Change]:
    if not isinstance(old_prop, dict) or not isinstance(new_prop, dict):
        return []

    changes: list[Change] = []

    # Property type
    old_type = old_prop.get("type")
    new_type = new_prop.get("type")
    if old_type and new_type and old_type != new_type:
        changes.append(Change(ChangeKind.SCHEMA_PROPERTY_TYPE_CHANGED, BREAKING, path, method, f"{schema_path} type changed from {old_type} to {new_type}", old_value=old_type, new_value=new_type, schema_path=schema_path))

    # Property format
    old_format = old_prop.get("format")
    new_format = new_prop.get("format")
    if old_format and new_format and old_format != new_format:
        changes.append(Change(ChangeKind.SCHEMA_FORMAT_CHANGED, BREAKING, path, method, f"{schema_path} format changed from {old_format} to {new_format}", old_value=old_format, new_value=new_format, schema_path=schema_path))

    # Property enum
    changes.extend(_diff_enum(old_prop, new_prop, path, method, schema_path))

    # Nested object
    if old_prop.get("type") == "object" or "properties" in old_prop or "properties" in new_prop:
        changes.extend(diff_schemas(old_prop, new_prop, path, method, schema_path, depth=depth + 1, max_depth=max_depth))

    # Array items
    if old_prop.get("type") == "array" or new_prop.get("type") == "array":
        old_items = old_prop.get("items")
        new_items = new_prop.get("items")
        if old_items and new_items:
            changes.extend(diff_schemas(old_items, new_items, path, method, f"{schema_path}[]", depth=depth + 1, max_depth=max_depth))

    return changes


# ── Enum diff ───────────────────────────────────────────────────────────────


def _diff_enum(old: dict, new: dict, path: str, method: str, loc: str) -> list[Change]:
    changes: list[Change] = []
    old_enum = set(old.get("enum") or [])
    new_enum = set(new.get("enum") or [])
    if old_enum and new_enum and old_enum != new_enum:
        removed = old_enum - new_enum
        added = new_enum - old_enum
        if removed:
            changes.append(Change(ChangeKind.ENUM_VALUE_REMOVED, BREAKING, path, method, f"{loc} enum values removed: {sorted(removed)}", old_value=sorted(removed), schema_path=loc))
        if added:
            changes.append(Change(ChangeKind.ENUM_VALUE_ADDED, ADDITIVE, path, method, f"{loc} enum values added: {sorted(added)}", new_value=sorted(added), schema_path=loc))
    elif old_enum and not new_enum:
        changes.append(Change(ChangeKind.ENUM_VALUE_REMOVED, BREAKING, path, method, f"{loc} enum removed", old_value=sorted(old_enum), schema_path=loc))
    elif not old_enum and new_enum:
        changes.append(Change(ChangeKind.ENUM_VALUE_ADDED, ADDITIVE, path, method, f"{loc} enum added", new_value=sorted(new_enum), schema_path=loc))
    return changes


# ── Constraints diff ────────────────────────────────────────────────────────


def _diff_constraints(old: dict, new: dict, path: str, method: str, loc: str) -> list[Change]:
    """Diff all JSON Schema constraint keywords."""
    changes: list[Change] = []
    constraints = [
        ("minimum", ChangeKind.SCHEMA_MIN_CHANGED),
        ("maximum", ChangeKind.SCHEMA_MAX_CHANGED),
        ("exclusiveMinimum", ChangeKind.SCHEMA_EXCLUSIVE_MIN_CHANGED),
        ("exclusiveMaximum", ChangeKind.SCHEMA_EXCLUSIVE_MAX_CHANGED),
        ("minLength", ChangeKind.SCHEMA_MIN_LENGTH_CHANGED),
        ("maxLength", ChangeKind.SCHEMA_MAX_LENGTH_CHANGED),
        ("pattern", ChangeKind.SCHEMA_PATTERN_CHANGED),
        ("minItems", ChangeKind.SCHEMA_MIN_ITEMS_CHANGED),
        ("maxItems", ChangeKind.SCHEMA_MAX_ITEMS_CHANGED),
        ("uniqueItems", ChangeKind.SCHEMA_UNIQUE_ITEMS_CHANGED),
        ("minProperties", ChangeKind.SCHEMA_MIN_PROPERTIES_CHANGED),
        ("maxProperties", ChangeKind.SCHEMA_MAX_PROPERTIES_CHANGED),
        ("multipleOf", ChangeKind.SCHEMA_MULTIPLE_OF_CHANGED),
    ]
    for key, kind in constraints:
        old_val = old.get(key)
        new_val = new.get(key)
        if old_val is not None and new_val is not None and old_val != new_val:
            changes.append(Change(kind, BREAKING, path, method, f"{loc} {key} changed from {old_val} to {new_val}", old_value=old_val, new_value=new_val, schema_path=loc))
        elif old_val is None and new_val is not None:
            changes.append(Change(kind, BREAKING, path, method, f"{loc} {key} set to {new_val}", new_value=new_val, schema_path=loc))
        elif old_val is not None and new_val is None:
            changes.append(Change(kind, BREAKING, path, method, f"{loc} {key} removed (was {old_val})", old_value=old_val, schema_path=loc))
    return changes


# ── Composition diff ────────────────────────────────────────────────────────


def _diff_composition(old: dict, new: dict, path: str, method: str, loc: str, depth: int, max_depth: int) -> list[Change]:
    """Diff allOf/oneOf/anyOf/not composition."""
    changes: list[Change] = []

    for keyword, add_kind, remove_kind, change_kind in [
        ("allOf", ChangeKind.SCHEMA_ALLOF_ADDED, ChangeKind.SCHEMA_ALLOF_REMOVED, ChangeKind.SCHEMA_ALLOF_SCHEMA_CHANGED),
        ("oneOf", ChangeKind.SCHEMA_ONEOF_ADDED, ChangeKind.SCHEMA_ONEOF_REMOVED, ChangeKind.SCHEMA_ONEOF_SCHEMA_CHANGED),
        ("anyOf", ChangeKind.SCHEMA_ANYOF_ADDED, ChangeKind.SCHEMA_ANYOF_REMOVED, ChangeKind.SCHEMA_ANYOF_SCHEMA_CHANGED),
    ]:
        old_val = old.get(keyword) or []
        new_val = new.get(keyword) or []
        if isinstance(old_val, list) and isinstance(new_val, list):
            if not old_val and new_val:
                changes.append(Change(add_kind, WARNING, path, method, f"{loc} {keyword} added"))
            elif old_val and not new_val:
                changes.append(Change(remove_kind, WARNING, path, method, f"{loc} {keyword} removed"))
            elif old_val != new_val:
                changes.append(Change(change_kind, WARNING, path, method, f"{loc} {keyword} changed"))

    # not composition
    old_not = old.get("not")
    new_not = new.get("not")
    if old_not != new_not and (old_not or new_not):
        changes.append(Change(ChangeKind.SCHEMA_NOT_CHANGED, WARNING, path, method, f"{loc} 'not' composition changed"))

    # additionalProperties
    old_ap = old.get("additionalProperties")
    new_ap = new.get("additionalProperties")
    if old_ap != new_ap and (old_ap is not None or new_ap is not None):
        changes.append(Change(ChangeKind.ADDITIONAL_PROPERTIES_CHANGED, BREAKING, path, method, f"{loc} additionalProperties changed", old_value=old_ap, new_value=new_ap, schema_path=loc))

    # discriminator
    old_disc = old.get("discriminator")
    new_disc = new.get("discriminator")
    if old_disc != new_disc and (old_disc or new_disc):
        changes.append(Change(ChangeKind.SCHEMA_DISCRIMINATOR_CHANGED, WARNING, path, method, f"{loc} discriminator changed"))

    return changes


# ── Metadata diff ───────────────────────────────────────────────────────────


def _diff_metadata(old: dict, new: dict, path: str, method: str, loc: str) -> list[Change]:
    """Diff schema metadata: nullable, readOnly, writeOnly, deprecated, default, example, title, description."""
    changes: list[Change] = []
    metadata = [
        ("nullable", ChangeKind.SCHEMA_NULLABLE_CHANGED),
        ("readOnly", ChangeKind.SCHEMA_READ_ONLY_CHANGED),
        ("writeOnly", ChangeKind.SCHEMA_WRITE_ONLY_CHANGED),
        ("deprecated", ChangeKind.SCHEMA_DEPRECATED_CHANGED),
        ("default", ChangeKind.SCHEMA_DEFAULT_CHANGED),
        ("example", ChangeKind.SCHEMA_EXAMPLE_CHANGED),
        ("title", ChangeKind.SCHEMA_TITLE_CHANGED),
        ("description", ChangeKind.SCHEMA_DESCRIPTION_CHANGED),
    ]
    for key, kind in metadata:
        old_val = old.get(key)
        new_val = new.get(key)
        if old_val != new_val and (old_val is not None or new_val is not None):
            changes.append(Change(kind, WARNING, path, method, f"{loc} {key} changed", old_value=old_val, new_value=new_val, schema_path=loc))
    return changes
