from app.detection.diff import diff_specs
from app.detection.models import ADDITIVE, BREAKING


def spec(paths):
    return {"openapi": "3.0.3", "paths": paths}


def op(parameters=None, responses=None):
    return {
        "summary": "x",
        "parameters": parameters or [],
        "responses": responses or {"200": {"description": "ok"}},
    }


def test_removed_endpoint_is_breaking():
    changes = diff_specs(spec({"/repos/{owner}/{repo}": {"get": op()}}), spec({}))
    assert len(changes) == 1
    c = changes[0]
    assert (c.kind, c.severity, c.method, c.path) == ("endpoint_removed", BREAKING, "get", "/repos/{owner}/{repo}")


def test_added_endpoint_is_additive():
    changes = diff_specs(spec({}), spec({"/repos/new": {"get": op()}}))
    assert (changes[0].kind, changes[0].severity) == ("endpoint_added", ADDITIVE)


def test_param_removed_is_breaking():
    old = spec({"/a": {"get": op(parameters=[{"name": "per_page", "in": "query", "required": False}])}})
    new = spec({"/a": {"get": op()}})
    assert any(c.kind == "param_removed" for c in diff_specs(old, new))


def test_param_becomes_required_is_breaking():
    old = spec({"/a": {"get": op(parameters=[{"name": "q", "in": "query", "required": False}])}})
    new = spec({"/a": {"get": op(parameters=[{"name": "q", "in": "query", "required": True}])}})
    assert any(c.kind == "param_required" for c in diff_specs(old, new))


def test_param_type_change_is_breaking():
    old = spec({"/a": {"get": op(parameters=[{"name": "n", "in": "query", "schema": {"type": "integer"}}])}})
    new = spec({"/a": {"get": op(parameters=[{"name": "n", "in": "query", "schema": {"type": "string"}}])}})
    assert any(c.kind == "param_type_changed" for c in diff_specs(old, new))


def test_response_code_removed_is_breaking():
    old = spec({"/a": {"get": op(responses={"200": {}, "410": {}})}})
    new = spec({"/a": {"get": op(responses={"200": {}})}})
    assert any(c.kind == "response_code_removed" for c in diff_specs(old, new))


def test_description_changes_produce_no_changes():
    old = spec({"/a": {"get": {"summary": "old", "description": "old words", "parameters": [], "responses": {"200": {}}}}})
    new = spec({"/a": {"get": {"summary": "new", "description": "new words", "parameters": [], "responses": {"200": {}}}}})
    assert diff_specs(old, new) == []


def test_reordering_produces_no_changes():
    old = spec({"/b": {"get": op(parameters=[{"name": "z", "in": "query"}, {"name": "a", "in": "query"}])}, "/a": {"get": op()}})
    new = spec({"/a": {"get": op()}, "/b": {"get": op(parameters=[{"name": "a", "in": "query"}, {"name": "z", "in": "query"}])}})
    assert diff_specs(old, new) == []


def test_changes_are_sorted_by_path():
    changes = diff_specs(spec({"/z": {"get": op()}, "/a": {"get": op()}}), spec({}))
    assert [c.path for c in changes] == ["/a", "/z"]
