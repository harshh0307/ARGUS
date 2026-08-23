from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TokenBudget:
    """Manages token budgets for LLM calls to prevent context window overflow."""

    max_input_tokens: int = 120000  # Conservative default for gpt-4o-mini (128k)
    max_output_tokens: int = 4096
    chars_per_token: float = 4.0  # Rough estimate: ~4 chars per token for English code

    # Tracking
    total_input_tokens: int = field(default=0, init=False)
    total_output_tokens: int = field(default=0, init=False)
    calls: list[dict] = field(default_factory=list, init=False)

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count from text (rough heuristic)."""
        return max(1, int(len(text) / self.chars_per_token))

    def fits_in_budget(self, prompt: str, reserved_output: int | None = None) -> bool:
        """Check if prompt fits within the token budget."""
        reserved = reserved_output or self.max_output_tokens
        prompt_tokens = self.estimate_tokens(prompt)
        return prompt_tokens + reserved <= self.max_input_tokens

    def remaining_budget(self, prompt: str) -> int:
        """How many tokens are left for the response."""
        prompt_tokens = self.estimate_tokens(prompt)
        return max(0, self.max_input_tokens - prompt_tokens)

    def truncate_to_budget(
        self,
        content: str,
        target_line: int,
        radius: int = 3,
        prefix: str = "",
    ) -> str:
        """Truncate file content to fit within token budget.

        Returns only lines around the impact point, with optional prefix
        for imports or context.
        """
        lines = content.splitlines()
        total_tokens = self.estimate_tokens(content)

        # If content fits, return as-is
        if total_tokens <= self.max_input_tokens // 2:
            return content

        # Progressive truncation: start with tight radius, expand if needed
        for r in [radius, radius * 2, radius * 4, radius * 8]:
            start = max(0, target_line - 1 - r)
            end = min(len(lines), target_line - 1 + r + 1)
            truncated = "\n".join(f"{i + 1}: {lines[i]}" for i in range(start, end))
            if prefix:
                truncated = prefix + "\n" + truncated
            if self.estimate_tokens(truncated) <= self.max_input_tokens // 2:
                return truncated

        # Last resort: just the target line
        idx = min(target_line - 1, len(lines) - 1)
        result = f"{target_line}: {lines[idx]}"
        if prefix:
            result = prefix + "\n" + result
        return result

    def record(self, input_tokens: int, output_tokens: int, model: str) -> None:
        """Record token usage from an LLM call."""
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.calls.append({
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        })

    def summary(self) -> str:
        """Human-readable summary of token usage."""
        return (
            f"Tokens: {self.total_input_tokens} in / {self.total_output_tokens} out "
            f"({len(self.calls)} calls)"
        )

    def exceeds_budget(self, max_cost: float | None = None) -> bool:
        """Check if we've exceeded the budget."""
        if max_cost is not None:
            # Rough cost estimate: $0.15/1M input, $0.60/1M output for gpt-4o-mini
            cost = (self.total_input_tokens * 0.00015 + self.total_output_tokens * 0.0006) / 1000
            return cost > max_cost
        return self.total_input_tokens > self.max_input_tokens
