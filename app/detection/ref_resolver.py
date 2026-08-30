from __future__ import annotations

import copy


def resolve_refs(spec: dict, *, max_depth: int = 32) -> dict:
    """Deep-copy *spec* with all ``$ref`` pointers resolved inline.

    References are resolved against the root ``components`` section.
    Circular references are detected and replaced with an empty object
    to prevent infinite recursion.

    The original ``$ref`` value is preserved as ``_ref_source`` metadata
    on each resolved node so callers can trace provenance.
    """
    spec = copy.deepcopy(spec)
    _resolve_node(spec, spec, set(), depth=0, max_depth=max_depth)
    return spec


def _resolve_node(
    node: object,
    root: dict,
    seen: set[str],
    *,
    depth: int,
    max_depth: int,
) -> object:
    if depth > max_depth:
        return node

    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/"):
            if ref in seen:
                return {}
            target = _follow_ref(root, ref)
            if target is None:
                return node
            resolved = copy.deepcopy(target)
            resolved["_ref_source"] = ref
            seen.add(ref)
            _resolve_node(resolved, root, seen, depth=depth + 1, max_depth=max_depth)
            seen.discard(ref)
            return resolved

        for key in list(node):
            node[key] = _resolve_node(node[key], root, seen, depth=depth + 1, max_depth=max_depth)
        return node

    if isinstance(node, list):
        return [_resolve_node(item, root, seen, depth=depth + 1, max_depth=max_depth) for item in node]

    return node


def _follow_ref(root: dict, ref: str) -> dict | None:
    """Walk a JSON-pointer ``#/a/b/c`` path against *root* and return the target node."""
    parts = ref.lstrip("#/").split("/")
    current: object = root
    for part in parts:
        part = part.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current if isinstance(current, dict) else None
