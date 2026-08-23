
from app.fix.cost_tracker import MODEL_COSTS, CostTracker


class TestCostTracker:
    def test_record(self):
        t = CostTracker()
        t.record(1000, 500, "gpt-4o-mini")
        assert t.total_input_tokens == 1000
        assert t.total_output_tokens == 500
        assert t.total_cost > 0

    def test_record_multiple(self):
        t = CostTracker()
        t.record(100, 50, "gpt-4o-mini")
        t.record(200, 100, "gpt-4o")
        assert t.total_input_tokens == 300
        assert t.total_output_tokens == 150
        assert len(t.calls) == 2

    def test_exceeds_budget_cost(self):
        t = CostTracker(max_cost_per_run=0.0001)
        t.record(100000, 100000, "gpt-4o")
        assert t.exceeds_budget() is True

    def test_exceeds_budget_tokens(self):
        t = CostTracker(max_tokens_per_run=100)
        t.record(200, 100, "gpt-4o-mini")
        assert t.exceeds_budget() is True

    def test_not_exceeds(self):
        t = CostTracker(max_cost_per_run=100, max_tokens_per_run=100000)
        t.record(100, 50, "gpt-4o-mini")
        assert t.exceeds_budget() is False

    def test_unknown_model(self):
        t = CostTracker()
        t.record(1000, 500, "unknown-model")
        assert t.total_input_tokens == 1000
        assert t.total_cost >= 0

    def test_free_model(self):
        t = CostTracker()
        t.record(1000, 500, "nvidia/nemotron-3-ultra-550b-a55b:free")
        assert t.total_cost == 0.0

    def test_summary(self):
        t = CostTracker()
        t.record(100, 50, "gpt-4o-mini")
        s = t.summary()
        assert "Tokens" in s
        assert "Cost" in s
        assert "Calls" in s

    def test_by_model(self):
        t = CostTracker()
        t.record(100, 50, "gpt-4o-mini")
        t.record(200, 100, "gpt-4o-mini")
        t.record(100, 50, "gpt-4o")
        b = t.by_model()
        assert "gpt-4o-mini" in b
        assert b["gpt-4o-mini"]["calls"] == 2
        assert "gpt-4o" in b
        assert b["gpt-4o"]["calls"] == 1

    def test_zero_tokens(self):
        t = CostTracker()
        t.record(0, 0, "gpt-4o-mini")
        assert t.total_input_tokens == 0
        assert t.total_cost == 0.0

    def test_large_token_count(self):
        t = CostTracker(max_cost_per_run=100, max_tokens_per_run=10000000)
        t.record(1000000, 500000, "gpt-4o-mini")
        assert t.total_input_tokens == 1000000
        assert t.total_cost > 0

    def test_summary_after_multiple(self):
        t = CostTracker()
        t.record(100, 50, "gpt-4o-mini")
        t.record(200, 100, "gpt-4o")
        s = t.summary()
        assert "300" in s

    def test_by_model_empty(self):
        t = CostTracker()
        assert t.by_model() == {}

    def test_gpt4o_cost(self):
        t = CostTracker()
        t.record(1000, 1000, "gpt-4o")
        assert t.total_cost > 0
        expected = 1000 * MODEL_COSTS["gpt-4o"]["input"] / 1e6 + 1000 * MODEL_COSTS["gpt-4o"]["output"] / 1e6
        assert abs(t.total_cost - expected) < 0.0001

    def test_gemini_flash_cost(self):
        t = CostTracker()
        t.record(1000, 1000, "gemini-1.5-flash")
        assert t.total_cost > 0
        expected = 1000 * MODEL_COSTS["gemini-1.5-flash"]["input"] / 1e6 + 1000 * MODEL_COSTS["gemini-1.5-flash"]["output"] / 1e6
        assert abs(t.total_cost - expected) < 0.0001
