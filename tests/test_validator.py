import pytest

from app.fix.models import PatchSuggestion
from app.fix.validator import PatchValidationError, PatchValidator, validate_patch_diff


@pytest.fixture
def validator():
    return PatchValidator()


@pytest.fixture
def impact():
    return {"file": "test.py", "line": 3, "change_kind": "endpoint_removed", "method": "get", "path": "/old"}


@pytest.fixture
def sample_content():
    return "import requests\n\nresponse = requests.get('https://api.example.com/old')\nprint(response.status_code)\n"


class TestPatchValidator:
    def test_valid_replace(self, validator, impact, sample_content):
        p = PatchSuggestion(file="test.py", line=3, action="replace", replacement="response = requests.get('https://api.example.com/new')")
        errors = validator.validate(p, sample_content, impact)
        assert errors == []

    def test_file_mismatch(self, validator, impact, sample_content):
        p = PatchSuggestion(file="wrong.py", line=3, action="replace", replacement="x")
        errors = validator.validate(p, sample_content, impact)
        assert any("file mismatch" in e for e in errors)

    def test_line_out_of_range(self, validator, impact, sample_content):
        p = PatchSuggestion(file="test.py", line=999, action="replace", replacement="x")
        errors = validator.validate(p, sample_content, impact)
        assert any("out of range" in e for e in errors)

    def test_line_zero(self, validator, impact, sample_content):
        p = PatchSuggestion(file="test.py", line=0, action="replace", replacement="x")
        errors = validator.validate(p, sample_content, impact)
        assert any("out of range" in e for e in errors)

    def test_line_mismatch_warning(self, validator, impact, sample_content):
        impact2 = dict(impact)
        impact2["line"] = 5
        p = PatchSuggestion(file="test.py", line=3, action="replace", replacement="x")
        errors = validator.validate(p, sample_content, impact2)
        assert any("line mismatch" in e for e in errors)

    def test_empty_replacement(self, validator, impact, sample_content):
        p = PatchSuggestion(file="test.py", line=3, action="replace", replacement="")
        errors = validator.validate(p, sample_content, impact)
        assert any("replacement is empty" in e for e in errors)

    def test_identical_replacement(self, validator, impact, sample_content):
        original_line = sample_content.splitlines()[2]
        p = PatchSuggestion(file="test.py", line=3, action="replace", replacement=original_line)
        errors = validator.validate(p, sample_content, impact)
        assert any("identical" in e for e in errors)

    def test_wildly_different_length(self, validator, impact, sample_content):
        p = PatchSuggestion(file="test.py", line=3, action="replace", replacement="x" * 500)
        errors = validator.validate(p, sample_content, impact)
        assert any("longer than original" in e for e in errors)

    def test_remove_valid(self, validator, impact, sample_content):
        p = PatchSuggestion(file="test.py", line=3, action="remove", replacement="")
        errors = validator.validate(p, sample_content, impact)
        assert errors == []

    def test_remove_only_line(self, validator, impact):
        p = PatchSuggestion(file="test.py", line=1, action="remove", replacement="")
        errors = validator.validate(p, "only line", impact)
        assert any("only line" in e for e in errors)

    def test_empty_content(self, validator, impact):
        p = PatchSuggestion(file="test.py", line=1, action="replace", replacement="x")
        errors = validator.validate(p, "", impact)
        assert any("empty" in e for e in errors)

    def test_validate_or_raise_valid(self, validator, impact, sample_content):
        p = PatchSuggestion(file="test.py", line=3, action="replace", replacement="response = requests.get('https://api.example.com/new')")
        validator.validate_or_raise(p, sample_content, impact)

    def test_validate_or_raise_invalid(self, validator, impact, sample_content):
        p = PatchSuggestion(file="wrong.py", line=3, action="replace", replacement="x")
        with pytest.raises(PatchValidationError):
            validator.validate_or_raise(p, sample_content, impact)

    def test_patch_validation_error_str(self):
        e = PatchValidationError(["err1", "err2"])
        assert "err1" in str(e)
        assert "err2" in str(e)

    def test_replace_longer_than_5x(self, validator, impact, sample_content):
        original_line = sample_content.splitlines()[2]
        p = PatchSuggestion(file="test.py", line=3, action="replace", replacement="a" * (len(original_line) * 6))
        errors = validator.validate(p, sample_content, impact)
        assert any("longer" in e for e in errors)

    def test_replace_valid_length(self, validator, impact, sample_content):
        original_line = sample_content.splitlines()[2]
        p = PatchSuggestion(file="test.py", line=3, action="replace", replacement=original_line + " extra")
        errors = validator.validate(p, sample_content, impact)
        # No length error
        assert not any("longer" in e for e in errors)


class TestValidatePatchDiff:
    def test_valid_diff(self):
        original = "line1\nline2\nline3\nline4\n"
        patched = "line1\nchanged\nline3\nline4\n"
        impact = {"line": 2}
        result = validate_patch_diff(original, patched, impact)
        assert result is None

    def test_too_many_removed(self):
        original = "line1\nline2\nline3\nline4\n"
        patched = "line1\n"
        impact = {"line": 2}
        result = validate_patch_diff(original, patched, impact)
        assert "too many lines removed" in result

    def test_too_many_added(self):
        original = "line1\n"
        patched = "line1\na\nb\nc\nd\ne\n"
        impact = {"line": 1}
        result = validate_patch_diff(original, patched, impact)
        assert "too many lines added" in result

    def test_no_changes(self):
        original = "line1\nline2\nline3\n"
        patched = "line1\nline2\nline3\n"
        impact = {"line": 2}
        result = validate_patch_diff(original, patched, impact)
        assert "no changes" in result

    def test_wrong_line_changed(self):
        original = "line1\nline2\nline3\nline4\n"
        patched = "line1\nline2\nchanged\nline4\n"
        impact = {"line": 1}
        result = validate_patch_diff(original, patched, impact)
        assert "not changed" in result

    def test_target_line_changed(self):
        original = "line1\nline2\nline3\nline4\n"
        patched = "line1\nchanged\nline3\nline4\n"
        impact = {"line": 2}
        result = validate_patch_diff(original, patched, impact)
        assert result is None

    def test_single_line_addition(self):
        original = "line1\nline2\nline3\n"
        patched = "line1\nline2\nnew\nline3\n"
        impact = {"line": 3}
        result = validate_patch_diff(original, patched, impact)
        assert result is None

    def test_single_line_removal(self):
        original = "line1\nline2\nline3\n"
        patched = "line1\nline3\n"
        impact = {"line": 2}
        result = validate_patch_diff(original, patched, impact)
        assert result is None

    def test_no_target_line(self):
        original = "line1\nline2\nline3\n"
        patched = "line1\nchanged\nline3\n"
        impact = {}
        result = validate_patch_diff(original, patched, impact)
        assert result is None
