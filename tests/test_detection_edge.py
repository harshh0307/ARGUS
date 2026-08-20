import pytest

from app.core.config import Settings
from app.detection.detect import run_detection
from app.detection.diff import diff_specs
from app.detection.normalize import normalize_spec
from app.ingestion.fetcher import FetchResult, SpecFetchError


def test_normalize_skips_non_dict_path_items():
    spec = {"paths": {"/a": "not-a-dict", "/b": None}}
    assert normalize_spec(spec) == {}


def test_normalize_skips_unknown_methods():
    spec = {"paths": {"/a": {"connect": {"responses": {}}}}}
    assert normalize_spec(spec) == {}


def test_normalize_skips_non_dict_operations():
    spec = {"paths": {"/a": {"get": "nope", "post": 42}}}
    assert normalize_spec(spec) == {}


def test_normalize_skips_params_without_name():
    operation = {"parameters": [{"in": "query", "required": True}, {"name": "", "in": "query"}]}
    normalized = normalize_spec({"paths": {"/a": {"get": operation}}})
    assert normalized["get /a"]["parameters"] == []


def test_normalize_param_without_location_gets_empty_string():
    operation = {"parameters": [{"name": "id", "schema": {"type": "string"}}]}
    normalized = normalize_spec({"paths": {"/a": {"get": operation}}})
    assert normalized["get /a"]["parameters"] == [("", "id", False, "string")]


def test_normalize_schema_not_dict_yields_none_type():
    operation = {"parameters": [{"name": "id", "in": "query", "schema": "string"}]}
    normalized = normalize_spec({"paths": {"/a": {"get": operation}}})
    assert normalized["get /a"]["parameters"] == [("query", "id", False, None)]


def test_normalize_sorts_parameters_by_location_then_name():
    operation = {
        "parameters": [
            {"name": "z", "in": "path"},
            {"name": "a", "in": "query"},
            {"name": "b", "in": "query"},
            {"name": "y", "in": "path"},
        ]
    }
    normalized = normalize_spec({"paths": {"/a": {"get": operation}}})
    names = [p[1] for p in normalized["get /a"]["parameters"]]
    assert names == ["y", "z", "a", "b"]


def test_normalize_operation_without_responses_key():
    operation = {"parameters": []}
    normalized = normalize_spec({"paths": {"/a": {"get": operation}}})
    assert normalized["get /a"]["responses"] == set()


def test_normalize_extracts_responses_and_required():
    operation = {
        "parameters": [{"name": "id", "in": "path", "required": True, "schema": {"type": "integer"}}],
        "responses": {"200": {}, "404": {}},
    }
    normalized = normalize_spec({"paths": {"/a": {"get": operation}}})
    assert normalized["get /a"]["parameters"] == [("path", "id", True, "integer")]
    assert normalized["get /a"]["responses"] == {"200", "404"}


def test_diff_empty_specs_produce_no_changes():
    assert diff_specs({}, {}) == []


def test_diff_param_location_change_is_removal_only():
    old = {"paths": {"/a": {"get": {"parameters": [{"name": "id", "in": "query", "schema": {"type": "string"}}]}}}}
    new = {"paths": {"/a": {"get": {"parameters": [{"name": "id", "in": "path", "schema": {"type": "string"}}]}}}}
    changes = diff_specs(old, new)
    kinds = {c.kind for c in changes}
    assert kinds == {"param_removed"}


def test_diff_new_parameter_is_not_breaking():
    old = {"paths": {"/a": {"get": {"parameters": []}}}}
    new = {"paths": {"/a": {"get": {"parameters": [{"name": "q", "in": "query", "schema": {"type": "string"}}]}}}}
    assert diff_specs(old, new) == []


def test_diff_type_change_from_none_is_ignored():
    old = {"paths": {"/a": {"get": {"parameters": [{"name": "id", "in": "query"}]}}}}
    new = {"paths": {"/a": {"get": {"parameters": [{"name": "id", "in": "query", "schema": {"type": "string"}}]}}}}
    assert diff_specs(old, new) == []


def test_diff_parameter_required_removed_is_not_breaking():
    old = {"paths": {"/a": {"get": {"parameters": [{"name": "id", "in": "query", "required": True, "schema": {"type": "string"}}]}}}}
    new = {"paths": {"/a": {"get": {"parameters": [{"name": "id", "in": "query", "schema": {"type": "string"}}]}}}}
    assert diff_specs(old, new) == []


def test_diff_response_code_added_is_not_breaking():
    old = {"paths": {"/a": {"get": {"responses": {"200": {}}}}}}
    new = {"paths": {"/a": {"get": {"responses": {"200": {}, "201": {}}}}}}
    assert diff_specs(old, new) == []


def test_diff_renamed_endpoint_reports_removed_and_added():
    old = {"paths": {"/old": {"get": {"responses": {"200": {}}}}}}
    new = {"paths": {"/new": {"get": {"responses": {"200": {}}}}}}
    changes = diff_specs(old, new)
    kinds = {c.kind for c in changes}
    assert kinds == {"endpoint_removed", "endpoint_added"}
    paths = {c.path for c in changes}
    assert paths == {"/old", "/new"}


def test_diff_operation_without_parameters_or_responses():
    old = {"paths": {"/a": {"get": {}}}}
    new = {"paths": {"/a": {"get": {}}}}
    assert diff_specs(old, new) == []


def test_diff_changes_sorted_by_path_method_kind():
    old = {
        "paths": {
            "/z": {"get": {"responses": {"200": {}}}},
            "/a": {"post": {"responses": {"200": {}}}, "get": {"responses": {"200": {}}}},
        }
    }
    new = {"paths": {"/a": {"get": {"responses": {"200": {}}}}}}
    changes = diff_specs(old, new)
    keys = [(c.path, c.method) for c in changes]
    assert keys == sorted(keys)
    assert keys == [("/a", "post"), ("/z", "get")]


def test_diff_tracks_duplicate_param_names_across_locations():
    old = {
        "paths": {
            "/a": {
                "get": {
                    "parameters": [
                        {"name": "id", "in": "query", "schema": {"type": "string"}},
                        {"name": "id", "in": "header", "schema": {"type": "string"}},
                    ]
                }
            }
        }
    }
    new = {
        "paths": {
            "/a": {
                "get": {
                    "parameters": [
                        {"name": "id", "in": "query", "schema": {"type": "string"}},
                    ]
                }
            }
        }
    }
    changes = diff_specs(old, new)
    assert [c.kind for c in changes] == ["param_removed"]
    assert "header" in changes[0].detail


def test_diff_http_method_case_sensitivity():
    old = {"paths": {"/a": {"GET": {"responses": {"200": {}}}}}}
    new = {"paths": {}}
    assert diff_specs(old, new) == []


class StubFetcher:
    def __init__(self, by_url):
        self.by_url = by_url

    def fetch(self, url, etag=None):
        content = self.by_url.get(url)
        if content is None:
            return None
        return FetchResult(content=content)


def test_run_detection_baselines_when_no_snapshot(tmp_path):
    fetcher = StubFetcher({"https://new": {"paths": {}}})
    settings = Settings(
        github_old_spec_url="",
        github_spec_url="https://new",
        snapshot_dir=str(tmp_path),
    )
    result = run_detection(settings, fetcher=fetcher)
    assert result["baselined"] is True
    assert result["old_digest"] is None
    assert result["new_digest"] is None
    assert result["changes"] == []


def test_run_detection_second_run_uses_stored_baseline(tmp_path):
    fetcher = StubFetcher({"https://new": {"paths": {"/x": {"get": {"responses": {"200": {}}}}}}})
    settings = Settings(
        github_old_spec_url="",
        github_spec_url="https://new",
        snapshot_dir=str(tmp_path),
    )
    first = run_detection(settings, fetcher=fetcher)
    assert first["baselined"] is True
    second = run_detection(settings, fetcher=fetcher)
    assert "baselined" not in second
    assert second["old_digest"] == second["new_digest"]
    assert second["old_digest"] is not None
    assert second["changes"] == []


def test_run_detection_raises_when_old_spec_unfetchable(tmp_path):
    fetcher = StubFetcher({"https://new": {"paths": {}}})
    settings = Settings(
        github_old_spec_url="https://old",
        github_spec_url="https://new",
        snapshot_dir=str(tmp_path),
    )
    with pytest.raises(SpecFetchError, match="could not fetch old spec"):
        run_detection(settings, fetcher=fetcher)


def test_run_detection_unchanged_spec_reports_no_changes(tmp_path):
    old = {"paths": {"/gone": {"get": {"responses": {"200": {}}}}}}
    fetcher = StubFetcher({"https://old": old})
    settings = Settings(
        github_old_spec_url="https://old",
        github_spec_url="https://new",
        snapshot_dir=str(tmp_path),
    )
    result = run_detection(settings, fetcher=fetcher)
    assert result["old_digest"] == result["new_digest"]
    assert result["changes"] == []
    assert result["breaking_count"] == 0


def test_run_detection_etag_passed_to_fetcher(tmp_path):
    calls = []

    class RecordingFetcher:
        def fetch(self, url, etag=None):
            calls.append((url, etag))
            return FetchResult(content={"paths": {}}, etag='"e1"')

    settings = Settings(
        github_old_spec_url="https://old",
        github_spec_url="https://new",
        snapshot_dir=str(tmp_path),
    )
    fetcher = RecordingFetcher()
    run_detection(settings, fetcher=fetcher, store=None)
    assert calls == [("https://old", None), ("https://new", None)]