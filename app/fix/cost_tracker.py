from __future__ import annotations

from dataclasses import dataclass, field

# Approximate costs per 1M tokens (USD) by model
MODEL_COSTS: dict[str, dict[str, float]] = {
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o": {"input": 5.00, "output": 15.00},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
    "gemini-1.5-flash": {"input": 0.075, "output": 0.30},
    "gemini-1.5-pro": {"input": 1.25, "output": 5.00},
    "nvidia/nemotron-3-ultra-550b-a55b:free": {"input": 0.0, "output": 0.0},
}


@dataclass
class CostTracker:
    """Tracks LLM token usage and costs."""

    max_cost_per_run: float = 1.0  # Default $1 max per run
    max_tokens_per_run: int = 500000  # Default 500k tokens max

    # Tracking
    total_input_tokens: int = field(default=0, init=False)
    total_output_tokens: int = field(default=0, init=False)
    total_cost: float = field(default=0.0, init=False)
    calls: list[dict] = field(default_factory=list, init=False)

    def record(
        self,
        input_tokens: int,
        output_tokens: int,
        model: str,
    ) -> None:
        """Record token usage from an LLM call."""
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens

        # Calculate cost
        costs = MODEL_COSTS.get(model, MODEL_COSTS.get("gpt-4o-mini"))
        cost = 0.0
        if costs:
            cost = (
                input_tokens * costs["input"] / 1_000_000
                + output_tokens * costs["output"] / 1_000_000
            )
        self.total_cost += cost

        self.calls.append({
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost": cost,
        })

    def exceeds_budget(self) -> bool:
        """Check if we've exceeded the cost or token budget."""
        return self.total_cost > self.max_cost_per_run or (
            self.total_input_tokens + self.total_output_tokens
        ) > self.max_tokens_per_run

    def summary(self) -> str:
        """Human-readable summary of usage."""
        total_tokens = self.total_input_tokens + self.total_output_tokens
        return (
            f"Tokens: {self.total_input_tokens:,} in / {self.total_output_tokens:,} out "
            f"({total_tokens:,} total) | Cost: ${self.total_cost:.4f} | "
            f"Calls: {len(self.calls)}"
        )

    def by_model(self) -> dict[str, dict[str, int]]:
        """Breakdown by model."""
        breakdown: dict[str, dict[str, int]] = {}
        for call in self.calls:
            model = call["model"]
            if model not in breakdown:
                breakdown[model] = {"input_tokens": 0, "output_tokens": 0, "calls": 0}
            breakdown[model]["input_tokens"] += call["input_tokens"]
            breakdown[model]["output_tokens"] += call["output_tokens"]
            breakdown[model]["calls"] += 1
        return breakdown
