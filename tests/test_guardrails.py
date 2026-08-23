
from app.fix.token_budget import TokenBudget


class TestTokenBudget:
    def test_estimate_tokens(self):
        b = TokenBudget(max_input_tokens=1000)
        assert b.estimate_tokens("hello world") > 0

    def test_estimate_tokens_empty(self):
        b = TokenBudget(max_input_tokens=1000)
        # estimate_tokens returns max(1, ...) for empty string
        assert b.estimate_tokens("") >= 0

    def test_estimate_tokens_chinese(self):
        b = TokenBudget(max_input_tokens=1000)
        assert b.estimate_tokens("你好世界") > 0

    def test_fits_in_budget_short(self):
        # Need budget large enough for text + reserved_output (4096)
        b = TokenBudget(max_input_tokens=10000, max_output_tokens=100)
        assert b.fits_in_budget("hello") is True

    def test_fits_in_budget_long(self):
        b = TokenBudget(max_input_tokens=10, max_output_tokens=0)
        # Need more than 10 tokens worth of text (> 40 chars)
        assert b.fits_in_budget("x" * 100) is False

    def test_fits_in_budget_exact(self):
        b = TokenBudget(max_input_tokens=5000, max_output_tokens=100)
        assert b.fits_in_budget("x" * 3000) is True

    def test_truncate_to_budget_small(self):
        b = TokenBudget(max_input_tokens=1000)
        result = b.truncate_to_budget("line1\nline2\nline3\nline4\nline5", 3, radius=1)
        # Content is small enough to not be truncated
        assert "line1" in result or "2:" in result

    def test_truncate_to_budget_large(self):
        b = TokenBudget(max_input_tokens=20)
        lines = "\n".join([f"line {i}" for i in range(100)])
        result = b.truncate_to_budget(lines, 50, radius=2)
        # Should contain line numbers around the target
        assert "line 49" in result or "line 50" in result or "line 51" in result

    def test_truncate_to_budget_no_truncation_needed(self):
        b = TokenBudget(max_input_tokens=10000)
        lines = "\n".join([f"line {i}" for i in range(20)])
        result = b.truncate_to_budget(lines, 5, radius=10)
        # Small content returned as-is
        assert "line 0" in result

    def test_truncate_to_budget_edge_case(self):
        b = TokenBudget(max_input_tokens=50)
        lines = "\n".join([f"line {i}" for i in range(200)])
        result = b.truncate_to_budget(lines, 1, radius=5)
        assert "line 0" in result or "line 1" in result

    def test_truncate_to_budget_line_1(self):
        b = TokenBudget(max_input_tokens=50)
        lines = "\n".join([f"line {i}" for i in range(200)])
        result = b.truncate_to_budget(lines, 1, radius=2)
        assert "line 0" in result or "line 1" in result

    def test_truncate_to_budget_line_last(self):
        b = TokenBudget(max_input_tokens=50)
        lines = "\n".join([f"line {i}" for i in range(200)])
        result = b.truncate_to_budget(lines, 200, radius=2)
        assert "line 199" in result

    def test_max_input_tokens_0(self):
        b = TokenBudget(max_input_tokens=0)
        assert b.fits_in_budget("anything") is False

    def test_large_radius(self):
        b = TokenBudget(max_input_tokens=50)
        lines = "\n".join([f"line {i}" for i in range(200)])
        result = b.truncate_to_budget(lines, 100, radius=500)
        assert len(result) > 0

    def test_truncate_to_budget_radius_exceeds_start(self):
        b = TokenBudget(max_input_tokens=50)
        lines = "\n".join([f"line {i}" for i in range(200)])
        result = b.truncate_to_budget(lines, 2, radius=5)
        assert "line 0" in result

    def test_truncate_to_budget_radius_exceeds_end(self):
        b = TokenBudget(max_input_tokens=50)
        lines = "\n".join([f"line {i}" for i in range(200)])
        result = b.truncate_to_budget(lines, 199, radius=5)
        assert "line 199" in result

    def test_truncate_to_budget_exact_token_limit(self):
        b = TokenBudget(max_input_tokens=20)
        lines = "\n".join([f"line {i}" for i in range(200)])
        result = b.truncate_to_budget(lines, 100, radius=0)
        assert len(result) > 0

    def test_fits_in_budget_boundary(self):
        b = TokenBudget(max_input_tokens=5000, max_output_tokens=100)
        assert b.fits_in_budget("hello") is True

    def test_estimate_tokens_consistency(self):
        b = TokenBudget(max_input_tokens=1000)
        t1 = b.estimate_tokens("hello")
        t2 = b.estimate_tokens("hello world")
        assert t2 > t1

    def test_empty_line_in_truncate(self):
        b = TokenBudget(max_input_tokens=200)
        lines = "line1\n\nline3\n\nline5"
        result = b.truncate_to_budget(lines, 3, radius=1)
        assert "line1" in result
        assert "line3" in result
        assert "line5" in result

    def test_summary(self):
        b = TokenBudget()
        b.record(100, 50, "gpt-4o-mini")
        s = b.summary()
        assert "100" in s
        assert "50" in s

    def test_exceeds_budget(self):
        b = TokenBudget(max_input_tokens=100)
        b.record(200, 0, "gpt-4o-mini")
        assert b.exceeds_budget() is True

    def test_exceeds_budget_with_cost(self):
        b = TokenBudget()
        b.record(1000000, 0, "gpt-4o-mini")
        assert b.exceeds_budget(max_cost=0.001) is True

    def test_remaining_budget(self):
        b = TokenBudget(max_input_tokens=1000)
        remaining = b.remaining_budget("hello")
        assert remaining > 0

    def test_remaining_budget_overflow(self):
        b = TokenBudget(max_input_tokens=100)
        remaining = b.remaining_budget("x" * 10000)
        assert remaining == 0
