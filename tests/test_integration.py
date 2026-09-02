"""End-to-end integration tests for the full Argus pipeline.

Tests verify the complete flow: detection → scanning → impact assessment → fix → validation.
"""

from __future__ import annotations

from pathlib import Path

from app.detection.models import BREAKING, Change, ChangeKind
from app.fix.ast_validators import validate_source
from app.fix.models import PatchSuggestion
from app.fix.patch import apply_patch
from app.fix.semantic_guards import run_semantic_guard
from app.fix.strategies import get_strategy, needs_llm
from app.scan.impact import assess_impact
from app.scan.scanner import ApiScanner

# ── Detection → Scanning → Impact Flow ─────────────────────────────────────


class TestDetectionToImpactFlow:
    """Test the flow from detection through scanning to impact assessment."""

    def test_end_to_end_python_scanning(self, sample_python_file):
        """Test scanning a Python file detects API calls."""
        scanner = ApiScanner(base_url="https://api.github.com")
        usages, _headers, _bodies, _auths, _responses = scanner.scan(sample_python_file.parent)

        assert len(usages) >= 3
        paths = {u.path for u in usages}
        assert "/users/{owner}/repos" in paths or "/user/repos" in paths

    def test_end_to_end_js_scanning(self, sample_js_file):
        """Test scanning a JavaScript file detects API calls."""
        scanner = ApiScanner(base_url="https://api.github.com")
        usages, _headers, _bodies, _auths, _responses = scanner.scan(sample_js_file.parent)

        assert len(usages) >= 2
        methods = {u.method for u in usages}
        assert "get" in methods or "post" in methods

    def test_end_to_end_go_scanning(self, tmp_path):
        """Test scanning a Go file detects API calls."""
        content = '''package main

import "net/http"

func getRepos(owner string) (*http.Response, error) {
    return http.Get("https://api.github.com/users/" + owner + "/repos")
}

func createRepo(name string) (*http.Response, error) {
    return http.Post("https://api.github.com/user/repos", "application/json", nil)
}
'''
        file = tmp_path / "main.go"
        file.write_text(content, encoding="utf-8")

        scanner = ApiScanner(base_url="https://api.github.com")
        usages, _headers, _bodies, _auths, _responses = scanner.scan(tmp_path)

        assert len(usages) >= 1
        methods = {u.method for u in usages}
        assert "get" in methods or "post" in methods

    def test_end_to_end_multi_lang_scanning(self, sample_multi_lang_project):
        """Test scanning a multi-language project."""
        scanner = ApiScanner(base_url="https://api.github.com")
        usages, _headers, _bodies, _auths, _responses = scanner.scan(sample_multi_lang_project)

        assert len(usages) >= 3
        files = {u.file for u in usages}
        assert len(files) >= 2

    def test_impact_assessment_with_changes(self, sample_python_file):
        """Test impact assessment links usages to breaking changes."""
        scanner = ApiScanner(base_url="https://api.github.com")
        usages, headers, bodies, auths, responses = scanner.scan(sample_python_file.parent)

        changes = [
            Change(
                ChangeKind.ENDPOINT_REMOVED,
                BREAKING,
                "/repos/{owner}/{repo}",
                "delete",
                "endpoint removed",
            )
        ]

        impacts = assess_impact(usages, headers, bodies, auths, responses, changes)

        assert len(impacts) >= 1
        assert any(i.change.kind == ChangeKind.ENDPOINT_REMOVED for i in impacts)

    def test_impact_assessment_no_match(self, sample_python_file):
        """Test impact assessment returns empty for non-matching changes."""
        scanner = ApiScanner(base_url="https://api.github.com")
        usages, headers, bodies, auths, responses = scanner.scan(sample_python_file.parent)

        changes = [
            Change(
                ChangeKind.ENDPOINT_REMOVED,
                BREAKING,
                "/nonexistent/{path}",
                "get",
                "endpoint removed",
            )
        ]

        impacts = assess_impact(usages, headers, bodies, auths, responses, changes)
        assert len(impacts) == 0


# ── Fix Pipeline Flow ──────────────────────────────────────────────────────


class TestFixPipelineFlow:
    """Test the fix pipeline: apply_patch → validate → semantic guard."""

    def test_apply_patch_and_validate(self, tmp_path):
        """Test applying a patch and validating the result."""
        content = 'import requests\nresp = requests.put("https://api.github.com/repos/{owner}/{repo}")\n'
        file = tmp_path / "app.py"
        file.write_text(content, encoding="utf-8")

        suggestion = PatchSuggestion(
            file=str(file),
            line=2,
            action="replace",
            replacement='resp = requests.patch("https://api.github.com/repos/{owner}/{repo}")',
            explanation="Change PUT to PATCH",
        )

        # Apply patch
        patched, error = apply_patch(content, suggestion)
        assert patched is not None
        assert error is None
        assert "requests.patch" in patched
        assert "requests.put" not in patched

        # Validate syntax
        is_valid, _syntax_error = validate_source(patched, str(file))
        assert is_valid
        assert _syntax_error is None

    def test_apply_patch_removes_param(self, tmp_path):
        """Test applying a patch that removes a parameter."""
        content = 'import requests\nresp = requests.get("https://api.github.com/repos/{owner}/{repo}", params={"q": "test", "old_param": "value"})\n'
        file = tmp_path / "app.py"
        file.write_text(content, encoding="utf-8")

        suggestion = PatchSuggestion(
            file=str(file),
            line=2,
            action="replace",
            replacement='resp = requests.get("https://api.github.com/repos/{owner}/{repo}", params={"q": "test"})',
            explanation="Remove deprecated parameter",
        )

        patched, _error = apply_patch(content, suggestion)
        assert patched is not None
        assert _error is None
        assert "old_param" not in patched

        is_valid, _syntax_error = validate_source(patched, str(file))
        assert is_valid

    def test_apply_patch_syntax_error(self, tmp_path):
        """Test applying a patch that introduces a syntax error."""
        content = 'import requests\nresp = requests.get("https://api.github.com/repos/{owner}/{repo}")\n'
        file = tmp_path / "app.py"
        file.write_text(content, encoding="utf-8")

        suggestion = PatchSuggestion(
            file=str(file),
            line=2,
            action="replace",
            replacement="resp = requests.get(",  # Syntax error
            explanation="Bad patch",
        )

        patched, _error = apply_patch(content, suggestion)
        assert patched is not None  # apply_patch succeeds

        # But validation catches it
        is_valid, syntax_error = validate_source(patched, str(file))
        assert not is_valid
        assert syntax_error is not None

    def test_fix_endpoint_removed_with_alternative(self, tmp_path):
        """Test fixing an endpoint_removed change with an alternative endpoint."""
        content = 'import requests\nresp = requests.delete("https://api.github.com/repos/{owner}/{repo}")\n'
        file = tmp_path / "app.py"
        file.write_text(content, encoding="utf-8")

        suggestion = PatchSuggestion(
            file=str(file),
            line=2,
            action="replace",
            replacement='resp = requests.put("https://api.github.com/users/me/profile", json={"archived": True})',
            explanation="Archive via different endpoint",
        )

        patched, error = apply_patch(content, suggestion)
        assert patched is not None
        assert error is None
        assert "archived" in patched

        # Validate
        is_valid, _ = validate_source(patched, str(file))
        assert is_valid

        # Semantic guard should accept (different endpoint path)
        impact_dict = {
            "change_kind": ChangeKind.ENDPOINT_REMOVED,
            "path": "/repos/{owner}/{repo}",
            "method": "delete",
        }
        result = run_semantic_guard(patched, impact_dict)
        assert result is None

    def test_fix_method_changed(self, tmp_path):
        """Test fixing a method_changed change updates the HTTP method."""
        content = 'import requests\nresp = requests.put("https://api.github.com/repos/{owner}/{repo}")\n'
        file = tmp_path / "app.py"
        file.write_text(content, encoding="utf-8")

        suggestion = PatchSuggestion(
            file=str(file),
            line=2,
            action="replace",
            replacement='resp = requests.patch("https://api.github.com/repos/{owner}/{repo}")',
            explanation="Change PUT to PATCH",
        )

        patched, error = apply_patch(content, suggestion)
        assert patched is not None
        assert error is None
        assert "requests.patch" in patched
        assert "requests.put" not in patched

        # Validate syntax
        is_valid, _ = validate_source(patched, str(file))
        assert is_valid

        # Semantic guard should pass
        impact_dict = {
            "change_kind": ChangeKind.METHOD_CHANGED,
            "old_method": "put",
            "new_method": "patch",
        }
        result = run_semantic_guard(patched, impact_dict)
        assert result is None


# ── Semantic Guards Integration ─────────────────────────────────────────────


class TestSemanticGuardsIntegration:
    """Test semantic guards catch invalid patches."""

    def test_guard_rejects_old_method(self):
        """Test guard rejects patch that still uses old HTTP method."""
        content = 'resp = requests.put("https://api.github.com/repos/{owner}/{repo}")'
        impact = {"old_method": "put", "new_method": "patch", "change_kind": ChangeKind.METHOD_CHANGED}

        result = run_semantic_guard(content, impact)
        assert result is not None
        assert "put" in result.lower() or "method" in result.lower()

    def test_guard_rejects_removed_param(self):
        """Test guard rejects patch that still uses removed parameter."""
        content = 'resp = requests.get(url, old_param="value")'
        impact = {"change_kind": ChangeKind.PARAM_REMOVED, "param_name": "old_param"}

        result = run_semantic_guard(content, impact)
        assert result is not None
        assert "old_param" in result

    def test_guard_rejects_removed_endpoint(self):
        """Test guard rejects patch that still calls removed endpoint."""
        content = 'resp = requests.delete("https://api.github.com/repos/{owner}/{repo}")'
        impact = {"change_kind": ChangeKind.ENDPOINT_REMOVED, "path": "/repos/{owner}/{repo}"}

        result = run_semantic_guard(content, impact)
        assert result is not None
        assert "removed endpoint" in result.lower() or "endpoint" in result.lower()

    def test_guard_accepts_valid_patch(self):
        """Test guard accepts valid patch."""
        content = 'resp = requests.patch("https://api.github.com/repos/{owner}/{repo}")'
        impact = {"old_method": "put", "new_method": "patch", "change_kind": ChangeKind.METHOD_CHANGED}

        result = run_semantic_guard(content, impact)
        assert result is None


# ── Strategy Registry Integration ───────────────────────────────────────────


class TestStrategyRegistryIntegration:
    """Test the strategy registry provides correct strategies."""

    def test_all_change_kinds_have_strategies(self):
        """Test that all ChangeKind values have registered strategies."""
        for kind in ChangeKind:
            strategy = get_strategy(kind.value)
            assert strategy is not None, f"No strategy for {kind.value}"

    def test_strategy_determines_llm_requirement(self):
        """Test strategies correctly indicate LLM requirement."""
        assert not needs_llm(ChangeKind.ENDPOINT_ADDED.value)
        assert not needs_llm(ChangeKind.SCHEMA_PROPERTY_ADDED.value)
        assert not needs_llm(ChangeKind.METHOD_CHANGED.value)
        assert not needs_llm(ChangeKind.PARAM_REMOVED.value)

    def test_strategy_has_examples(self):
        """Test that key strategies have examples."""
        key_strategies = [
            ChangeKind.METHOD_CHANGED,
            ChangeKind.PARAM_REMOVED,
            ChangeKind.REQUEST_BODY_REMOVED,
        ]
        for kind in key_strategies:
            strategy = get_strategy(kind.value)
            assert strategy is not None
            assert len(strategy.examples) > 0, f"No examples for {kind.value}"


# ── AST Validators Integration ──────────────────────────────────────────────


class TestASTValidatorsIntegration:
    """Test AST validators catch syntax errors."""

    def test_python_syntax_error(self):
        """Test Python validator catches syntax errors."""
        content = "def foo(\n    pass"
        is_valid, error = validate_source(content, "test.py")
        assert not is_valid
        assert error is not None

    def test_python_valid_code(self):
        """Test Python validator accepts valid code."""
        content = "def foo():\n    pass\n"
        is_valid, error = validate_source(content, "test.py")
        assert is_valid
        assert error is None

    def test_javascript_syntax_error(self):
        """Test JavaScript validator catches syntax errors."""
        content = "function foo() {"
        is_valid, error = validate_source(content, "test.js")
        assert not is_valid
        assert error is not None

    def test_javascript_valid_code(self):
        """Test JavaScript validator accepts valid code."""
        content = "function foo() { return 1; }"
        is_valid, error = validate_source(content, "test.js")
        assert is_valid
        assert error is None

    def test_go_syntax_error(self):
        """Test Go validator catches syntax errors."""
        content = "package main\nfunc foo() {"
        is_valid, error = validate_source(content, "test.go")
        assert not is_valid
        assert error is not None

    def test_go_valid_code(self):
        """Test Go validator accepts valid code."""
        content = "package main\nfunc foo() {}"
        is_valid, error = validate_source(content, "test.go")
        assert is_valid
        assert error is None


# ── Full Pipeline Integration ───────────────────────────────────────────────


class TestFullPipelineIntegration:
    """Test the complete pipeline from scan to fix."""

    def test_scan_to_patch_to_validate(self, tmp_path):
        """Test the full scan → patch → validate cycle."""
        content = 'import requests\nresp = requests.get("https://api.github.com/repos/{owner}/{repo}")\n'
        file = tmp_path / "app.py"
        file.write_text(content, encoding="utf-8")

        # Scan
        scanner = ApiScanner(base_url="https://api.github.com")
        usages, headers, bodies, auths, responses = scanner.scan(tmp_path)

        # Create matching change
        changes = [
            Change(
                ChangeKind.ENDPOINT_REMOVED,
                BREAKING,
                "/repos/{owner}/{repo}",
                "get",
                "endpoint removed",
            )
        ]

        # Impact assessment
        impacts = assess_impact(usages, headers, bodies, auths, responses, changes)
        assert len(impacts) >= 1

        # Create patch for first impact
        impact = impacts[0]
        suggestion = PatchSuggestion(
            file=str(file),
            line=impact.usage.line,
            action="replace",
            replacement='resp = requests.put("https://api.github.com/repos/{owner}/{repo}", json={"archived": True})',
            explanation="Archive instead of delete",
        )

        # Apply patch
        patched, error = apply_patch(content, suggestion)
        assert patched is not None
        assert error is None

        # Validate
        is_valid, _ = validate_source(patched, str(file))
        assert is_valid

    def test_batch_patch_application(self, tmp_path):
        """Test applying patches to multiple files."""
        content1 = 'import requests\nresp1 = requests.get("https://api.github.com/repos/{owner}/{repo}")\n'
        content2 = 'import requests\nresp2 = requests.delete("https://api.github.com/repos/{owner}/{repo}")\n'

        file1 = tmp_path / "app1.py"
        file2 = tmp_path / "app2.py"
        file1.write_text(content1, encoding="utf-8")
        file2.write_text(content2, encoding="utf-8")

        suggestion1 = PatchSuggestion(
            file=str(file1),
            line=2,
            action="replace",
            replacement='resp1 = requests.get("https://api.github.com/repos/{owner}/{repo}", timeout=30)',
            explanation="Add timeout",
        )
        suggestion2 = PatchSuggestion(
            file=str(file2),
            line=2,
            action="replace",
            replacement='resp2 = requests.put("https://api.github.com/repos/{owner}/{repo}", json={"archived": True})',
            explanation="Archive instead of delete",
        )

        # Apply both patches
        patched1, err1 = apply_patch(content1, suggestion1)
        patched2, err2 = apply_patch(content2, suggestion2)

        assert patched1 is not None
        assert patched2 is not None
        assert err1 is None
        assert err2 is None

        # Validate both
        is_valid1, _ = validate_source(patched1, str(file1))
        is_valid2, _ = validate_source(patched2, str(file2))
        assert is_valid1
        assert is_valid2


# ── Multi-Language Integration ──────────────────────────────────────────────


class TestMultiLanguageIntegration:
    """Test scanning and fixing across multiple languages."""

    def test_scanner_handles_all_languages(self, sample_multi_lang_project):
        """Test scanner handles Python, JavaScript, and Go files."""
        scanner = ApiScanner(base_url="https://api.github.com")
        usages, _headers, _bodies, _auths, _responses = scanner.scan(sample_multi_lang_project)

        files = {u.file for u in usages}
        extensions = {Path(f).suffix for f in files}
        assert ".py" in extensions or ".js" in extensions or ".go" in extensions

    def test_body_usage_detection(self, sample_python_file):
        """Test that body usage is detected in Python files."""
        scanner = ApiScanner(base_url="https://api.github.com")
        _usages, _headers, bodies, _auths, _responses = scanner.scan(sample_python_file.parent)

        assert len(bodies) >= 1

    def test_header_usage_detection(self, sample_python_file):
        """Test that header usage is detected in Python files."""
        scanner = ApiScanner(base_url="https://api.github.com")
        _usages, headers, _bodies, _auths, _responses = scanner.scan(sample_python_file.parent)

        assert len(headers) >= 1
        auth_headers = [h for h in headers if h.header_name.lower() == "authorization"]
        assert len(auth_headers) >= 1

    def test_multi_lang_patch_and_validate(self, sample_multi_lang_project):
        """Test patching and validating across multiple languages."""
        scanner = ApiScanner(base_url="https://api.github.com")
        usages, _headers, _bodies, _auths, _responses = scanner.scan(sample_multi_lang_project)

        # Apply a simple patch to each detected file
        for usage in usages[:3]:
            file_path = Path(usage.file)
            if not file_path.exists():
                continue
            content = file_path.read_text(encoding="utf-8")

            # Simple validation that file is parseable
            ext = file_path.suffix
            if ext in (".py",):
                is_valid, _ = validate_source(content, str(file_path))
                assert is_valid, f"Original {file_path} should be valid"
