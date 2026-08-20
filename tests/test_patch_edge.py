from app.fix.models import PatchSuggestion
from app.fix.patch import apply_patch, validate_javascript, validate_python, validate_source


def patch(action="replace", line=1, replacement="new"):
    return PatchSuggestion(file="a.py", line=line, action=action, replacement=replacement)


def test_apply_patch_line_zero_out_of_range():
    result, err = apply_patch("a\nb\n", patch(line=0))
    assert result is None
    assert err == "line 0 out of range (file has 2 lines)"


def test_apply_patch_line_beyond_file_out_of_range():
    result, err = apply_patch("a\n", patch(line=2))
    assert result is None
    assert err == "line 2 out of range (file has 1 lines)"


def test_apply_patch_empty_file_out_of_range():
    result, err = apply_patch("", patch(line=1))
    assert result is None
    assert "out of range" in err


def test_apply_patch_empty_replacement_rejected():
    result, err = apply_patch("a\nb\n", patch(replacement=""))
    assert result is None
    assert err == "replacement is empty"


def test_apply_patch_remove_last_line_without_trailing_newline():
    content, err = apply_patch("a\nb", patch(action="remove", line=2))
    assert err is None
    assert content == "a"


def test_apply_patch_remove_only_line():
    content, err = apply_patch("solo", patch(action="remove", line=1))
    assert err is None
    assert content == ""


def test_apply_patch_replace_preserves_no_trailing_newline():
    content, err = apply_patch("a\nb", patch(line=2, replacement="c"))
    assert err is None
    assert content == "a\nc"
    assert not content.endswith("\n")


def test_validate_javascript_balanced():
    assert validate_javascript("function f() { return 1; }") is None


def test_validate_javascript_strings_skipped():
    source = 'const s = "})]{(";\nconst t = \'{(")}\';\nlet ok = true;'
    assert validate_javascript(source) is None


def test_validate_javascript_template_literal_skipped():
    source = "const url = `https://x.com/${a ? 1 : 2}`;"
    assert validate_javascript(source) is None


def test_validate_javascript_unbalanced_open_brace():
    err = validate_javascript("function f() {")
    assert err is not None
    assert "unbalanced" in err
    assert err.startswith("unbalanced '{' opened")


def test_validate_javascript_unbalanced_close_paren():
    err = validate_javascript("const x = 1; )")
    assert err is not None
    assert err.startswith("unbalanced ')'")


def test_validate_javascript_mismatched_brackets():
    err = validate_javascript("const x = [1, 2);")
    assert err is not None
    assert "unbalanced" in err


def test_validate_javascript_unterminated_string():
    err = validate_javascript("const s = 'abc")
    assert err == "unterminated string literal"


def test_validate_javascript_unterminated_block_comment():
    err = validate_javascript("/* never closed")
    assert err == "unterminated block comment"


def test_validate_javascript_escaped_quote_ok():
    assert validate_javascript(r"const s = 'it\'s fine';") is None


def test_validate_source_routes_to_javascript():
    err = validate_source("const x = {", language="js")
    assert err is not None
    assert "unbalanced" in err


def test_validate_source_routes_to_python():
    assert validate_source("def f():\n    pass", language="py") is None
    err = validate_source("def f(:\n", language="py")
    assert err is not None
    assert err.startswith("SyntaxError")


def test_validate_python_preserves_syntax_error_line():
    err = validate_python("x = 1\ndef broken(:\n")
    assert err is not None
    assert "SyntaxError at line 2" in err


def test_apply_patch_replaces_middle_line_keeps_others():
    content, err = apply_patch("a\nb\nc\n", patch(line=2, replacement="B"))
    assert err is None
    assert content == "a\nB\nc\n"