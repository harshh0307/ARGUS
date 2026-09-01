"""Tests for ChangeKind enum, ChangeCategory, and updated Change model."""

from app.detection.models import (
    ADDITIVE,
    BREAKING,
    Change,
    ChangeCategory,
    ChangeKind,
    categorize_change,
)


class TestChangeKind:
    def test_all_members_have_values(self):
        for member in ChangeKind:
            assert isinstance(member.value, str)
            assert len(member.value) > 0

    def test_member_count(self):
        assert len(ChangeKind) == 146

    def test_str_enum_compatibility(self):
        """ChangeKind is a str enum — string comparisons work."""
        assert ChangeKind.ENDPOINT_REMOVED == "endpoint_removed"
        assert ChangeKind.METHOD_CHANGED == "method_changed"
        assert isinstance(ChangeKind.SCHEMA_TYPE_CHANGED, str)

    def test_no_duplicate_values(self):
        values = [m.value for m in ChangeKind]
        assert len(values) == len(set(values))


class TestChangeCategory:
    def test_all_members_have_values(self):
        for member in ChangeCategory:
            assert isinstance(member.value, str)

    def test_member_count(self):
        assert len(ChangeCategory) == 15


class TestCategoryMap:
    def test_all_kinds_mapped(self):
        mapped = set(_CATEGORY_MAP.keys())
        all_kinds = set(ChangeKind)
        assert mapped == all_kinds

    def test_endpoint_kinds(self):
        assert _CATEGORY_MAP[ChangeKind.ENDPOINT_ADDED] == ChangeCategory.ENDPOINT
        assert _CATEGORY_MAP[ChangeKind.ENDPOINT_REMOVED] == ChangeCategory.ENDPOINT
        assert _CATEGORY_MAP[ChangeKind.METHOD_CHANGED] == ChangeCategory.ENDPOINT

    def test_parameter_kinds(self):
        assert _CATEGORY_MAP[ChangeKind.PARAM_REMOVED] == ChangeCategory.PARAMETER
        assert _CATEGORY_MAP[ChangeKind.PARAM_REQUIRED] == ChangeCategory.PARAMETER
        assert _CATEGORY_MAP[ChangeKind.PARAM_TYPE_CHANGED] == ChangeCategory.PARAMETER

    def test_schema_kinds(self):
        assert _CATEGORY_MAP[ChangeKind.SCHEMA_TYPE_CHANGED] == ChangeCategory.SCHEMA
        assert _CATEGORY_MAP[ChangeKind.ENUM_VALUE_REMOVED] == ChangeCategory.SCHEMA

    def test_security_kinds(self):
        assert _CATEGORY_MAP[ChangeKind.OAUTH_SCOPE_REMOVED] == ChangeCategory.SECURITY
        assert _CATEGORY_MAP[ChangeKind.SECURITY_SCHEME_TYPE_CHANGED] == ChangeCategory.SECURITY


# Need to import _CATEGORY_MAP for the tests above
from app.detection.models import _CATEGORY_MAP


class TestCategorizeChange:
    def test_returns_category(self):
        cat = categorize_change(ChangeKind.ENDPOINT_REMOVED)
        assert cat == ChangeCategory.ENDPOINT

    def test_all_kinds_categorizable(self):
        for kind in ChangeKind:
            cat = categorize_change(kind)
            assert isinstance(cat, ChangeCategory)


class TestChangeModel:
    def test_construction_with_change_kind(self):
        c = Change(
            kind=ChangeKind.ENDPOINT_REMOVED,
            severity=BREAKING,
            path="/users/{id}",
            method="get",
            detail="endpoint removed",
        )
        assert c.kind == ChangeKind.ENDPOINT_REMOVED
        assert c.category == ChangeCategory.ENDPOINT

    def test_construction_with_string_kind(self):
        """Backward compatibility: string kind auto-categorizes."""
        c = Change("endpoint_removed", BREAKING, "/users", "get", "removed")
        assert c.kind == "endpoint_removed"
        assert c.category == ChangeCategory.ENDPOINT

    def test_new_fields(self):
        c = Change(
            kind=ChangeKind.METHOD_CHANGED,
            severity=BREAKING,
            path="/users",
            method="put",
            detail="PUT → PATCH",
            old_method="put",
            new_method="patch",
            confidence=0.95,
        )
        assert c.old_method == "put"
        assert c.new_method == "patch"
        assert c.confidence == 0.95

    def test_defaults(self):
        c = Change(
            kind=ChangeKind.PARAM_ADDED,
            severity=ADDITIVE,
            path="/users",
            method="get",
        )
        assert c.old_value is None
        assert c.new_value is None
        assert c.schema_path is None
        assert c.ref_source is None
        assert c.old_method is None
        assert c.new_method is None
        assert c.confidence == 1.0

    def test_frozen(self):
        c = Change(
            kind=ChangeKind.ENDPOINT_REMOVED,
            severity=BREAKING,
            path="/users",
            method="get",
        )
        try:
            c.kind = ChangeKind.ENDPOINT_ADDED  # type: ignore[misc]
            assert False, "Should be frozen"
        except AttributeError:
            pass

    def test_str_representation(self):
        c = Change(
            kind=ChangeKind.ENDPOINT_REMOVED,
            severity=BREAKING,
            path="/users/{id}",
            method="delete",
            detail="gone",
        )
        s = str(c)
        assert "breaking" in s
        assert "DELETE" in s
        assert "/users/{id}" in s
        assert "endpoint_removed" in s
