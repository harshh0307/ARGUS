"""Tests for fix models, strategies, AST validators, semantic guards, state, circuit breaker, token manager."""

import time
from unittest.mock import MagicMock

from app.fix.strategies import ChangeKind
from app.fix.ast_validators import (
    validate_csharp,
    validate_go,
    validate_java,
    validate_javascript,
    validate_php,
    validate_python,
    validate_ruby,
    validate_source,
)
from app.fix.circuit_breaker import CircuitBreaker, MultiLLMRouter
from app.fix.models import FixResult, FixStrategy, PatchSuggestion
from app.fix.semantic_guards import run_semantic_guard
from app.fix.strategies import (
    get_strategy,
    needs_llm,
    register_strategy,
)

# ── PatchSuggestion tests ───────────────────────────────────────────────────


class TestPatchSuggestion:
    def test_construction(self):
        p = PatchSuggestion(file="app.py", line=10)
        assert p.file == "app.py"
        assert p.line == 10
        assert p.action == "replace"

    def test_all_actions(self):
        for action in [
            "replace",
            "remove",
            "insert",
            "add_import",
            "remove_import",
            "rename",
        ]:
            p = PatchSuggestion(file="app.py", line=1, action=action)
            assert p.action == action

    def test_new_fields(self):
        p = PatchSuggestion(
            file="app.py",
            line=1,
            action="add_import",
            import_path="requests",
            explanation="Add missing import",
        )
        assert p.import_path == "requests"
        assert p.explanation == "Add missing import"

    def test_rename_fields(self):
        p = PatchSuggestion(
            file="app.py",
            line=1,
            action="rename",
            old_name="old_func",
            new_name="new_func",
        )
        assert p.old_name == "old_func"
        assert p.new_name == "new_func"


# ── FixResult tests ─────────────────────────────────────────────────────────


class TestFixResult:
    def test_success(self):
        r = FixResult(file="app.py", line=10, success=True)
        assert r.success
        assert r.error is None

    def test_failure(self):
        r = FixResult(file="app.py", line=10, success=False, error="syntax error")
        assert not r.success
        assert r.error == "syntax error"


# ── FixStrategy tests ───────────────────────────────────────────────────────


class TestFixStrategy:
    def test_construction(self):
        s = FixStrategy(kind="method_changed", description="test")
        assert s.kind == "method_changed"
        assert s.llm_required is False

    def test_with_validator(self):
        v = lambda c, i: True
        s = FixStrategy(kind="test", validator=v)
        assert s.validator("content", {}) is True


# ── Strategy Registry tests ─────────────────────────────────────────────────


class TestStrategyRegistry:
    def test_all_kinds_registered(self):
        for kind in ChangeKind:
            strategy = get_strategy(kind.value)
            assert strategy is not None, f"No strategy for {kind.value}"

    def test_get_strategy(self):
        s = get_strategy("method_changed")
        assert s is not None
        assert s.kind == "method_changed"

    def test_get_strategy_unknown(self):
        s = get_strategy("nonexistent_kind")
        assert s is None

    def test_needs_llm_endpoint_removed(self):
        assert needs_llm("endpoint_removed") is True

    def test_needs_llm_endpoint_added(self):
        assert needs_llm("endpoint_added") is False

    def test_needs_llm_method_changed(self):
        assert needs_llm("method_changed") is False

    def test_needs_llm_unknown(self):
        assert needs_llm("unknown_kind") is True

    def test_register_custom_strategy(self):
        custom = FixStrategy(kind="custom_test", description="custom")
        register_strategy(custom)
        assert get_strategy("custom_test") is custom


# ── AST Validator tests ─────────────────────────────────────────────────────


class TestPythonValidator:
    def test_valid(self):
        ok, err = validate_python("x = 1\nprint(x)")
        assert ok
        assert err is None

    def test_syntax_error(self):
        ok, err = validate_python("def foo(\n")
        assert not ok
        assert "SyntaxError" in err or "line" in err.lower()

    def test_unreachable_code(self):
        ok, _err = validate_python("def foo():\n    return 1\n    x = 2")
        assert not ok


class TestJavaScriptValidator:
    def test_valid(self):
        ok, _err = validate_javascript("const x = 1;\nconsole.log(x);")
        assert ok

    def test_unmatched_brace(self):
        ok, err = validate_javascript("function foo() {")
        assert not ok
        assert "Unclosed" in err

    def test_unmatched_close(self):
        ok, err = validate_javascript("function foo() }")
        assert not ok
        assert "Unmatched" in err

    def test_string_with_braces(self):
        ok, _err = validate_javascript('const x = "hello { world }";')
        assert ok


class TestGoValidator:
    def test_valid(self):
        ok, _err = validate_go("package main\nfunc main() {}")
        assert ok

    def test_missing_package(self):
        ok, err = validate_go("func main() {}")
        assert not ok
        assert "package" in err.lower()


class TestRubyValidator:
    def test_valid(self):
        ok, _err = validate_ruby("def foo\n  1\nend")
        assert ok

    def test_mismatched_end(self):
        ok, _err = validate_ruby("def foo\n  1")
        assert not ok


class TestJavaValidator:
    def test_valid(self):
        ok, _err = validate_java("public class Foo {}")
        assert ok

    def test_missing_class(self):
        ok, _err = validate_java("public static void main() {}")
        assert not ok


class TestPHPValidator:
    def test_valid(self):
        ok, _err = validate_php("<?php echo 'hello';")
        assert ok


class TestCSharpValidator:
    def test_valid(self):
        ok, _err = validate_csharp("namespace Foo { class Bar {} }")
        assert ok


class TestValidateSource:
    def test_python(self):
        ok, _err = validate_source("x = 1", "app.py")
        assert ok

    def test_unknown_extension(self):
        ok, _err = validate_source("anything", "app.xyz")
        assert ok  # unknown → skip


# ── Semantic Guard tests ────────────────────────────────────────────────────


class TestSemanticGuards:
    def test_method_changed_pass(self):
        impact = {"change_kind": "method_changed", "old_method": "put", "new_method": "patch"}
        result = run_semantic_guard("requests.patch(url, json=data)", impact)
        assert result is None

    def test_method_changed_fail(self):
        impact = {"change_kind": "method_changed", "old_method": "put", "new_method": "patch"}
        result = run_semantic_guard("requests.put(url, json=data)", impact)
        assert result is not None
        assert "put" in result

    def test_param_removed_pass(self):
        impact = {"change_kind": "param_removed", "param_name": "old_param"}
        result = run_semantic_guard("requests.get(url, params={'q': val})", impact)
        assert result is None

    def test_param_removed_fail(self):
        impact = {"change_kind": "param_removed", "param_name": "old_param"}
        result = run_semantic_guard("requests.get(url, old_param=val)", impact)
        assert result is not None

    def test_enum_removed_pass(self):
        impact = {"change_kind": "enum_value_removed", "old_value": "archived"}
        result = run_semantic_guard("status = 'active'", impact)
        assert result is None

    def test_enum_removed_fail(self):
        impact = {"change_kind": "enum_value_removed", "old_value": "archived"}
        result = run_semantic_guard("status = 'archived'", impact)
        assert result is not None

    def test_no_guard_registered(self):
        impact = {"change_kind": "info_title_changed"}
        result = run_semantic_guard("anything", impact)
        assert result is None


# ── Circuit Breaker tests ───────────────────────────────────────────────────


class TestCircuitBreaker:
    def test_initial_state_closed(self):
        cb = CircuitBreaker()
        assert cb.should_try("openai") is True

    def test_opens_after_threshold(self):
        cb = CircuitBreaker(failure_threshold=3)
        for _ in range(3):
            cb.record_failure("openai")
        assert cb.should_try("openai") is False

    def test_half_open_after_timeout(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)
        cb.record_failure("openai")
        cb.record_failure("openai")
        assert cb.should_try("openai") is False
        time.sleep(0.15)
        assert cb.should_try("openai") is True

    def test_success_resets(self):
        cb = CircuitBreaker(failure_threshold=2)
        cb.record_failure("openai")
        cb.record_success("openai")
        assert cb.should_try("openai") is True
        assert cb._failures["openai"] == 0

    def test_reset(self):
        cb = CircuitBreaker(failure_threshold=2)
        cb.record_failure("openai")
        cb.reset("openai")
        assert cb.should_try("openai") is True


class TestMultiLLMRouter:
    def test_uses_first_provider(self):
        mock_client = MagicMock()
        mock_client.invoke.return_value = "response"
        router = MultiLLMRouter([("openai", mock_client)])
        result = router.invoke("prompt")
        assert result == "response"
        mock_client.invoke.assert_called_once()

    def test_fallback_on_rate_limit(self):
        mock1 = MagicMock()
        mock1.invoke.side_effect = Exception("429 rate limit")
        mock2 = MagicMock()
        mock2.invoke.return_value = "fallback response"
        router = MultiLLMRouter([("openai", mock1), ("gemini", mock2)])
        result = router.invoke("prompt")
        assert result == "fallback response"

    def test_raises_when_all_exhausted(self):
        mock1 = MagicMock()
        mock1.invoke.side_effect = Exception("429 rate limit")
        mock2 = MagicMock()
        mock2.invoke.side_effect = Exception("429 rate limit")
        router = MultiLLMRouter([("openai", mock1), ("gemini", mock2)])
        try:
            router.invoke("prompt")
            assert False, "Should have raised"
        except RuntimeError as e:
            assert "exhausted" in str(e).lower()

    def test_provider_states(self):
        mock_client = MagicMock()
        router = MultiLLMRouter([("openai", mock_client)])
        states = router.get_provider_states()
        assert states["openai"] == "closed"
