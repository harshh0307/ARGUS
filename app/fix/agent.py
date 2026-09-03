from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.core.config import Settings
from app.fix.cost_tracker import CostTracker
from app.fix.errors import (
    classify_error,
)
from app.fix.models import FixResult, PatchSuggestion
from app.fix.patch import apply_patch, validate_source
from app.fix.prompt import build_prompt
from app.fix.token_budget import TokenBudget
from app.fix.validator import PatchValidator
from app.scan.impact import match_path
from app.scan.scanner import ApiScanner, language_for_file

RETRY_DELAY_RE = re.compile(r"retry in ([\d.]+)s")


def _retry_delay(exc: Exception, attempt: int) -> float:
    """Calculate retry delay with exponential backoff."""
    error_str = str(exc).lower()

    # Parse provider-specific retry-after hints
    match = RETRY_DELAY_RE.search(str(exc))
    if match:
        base_delay = float(match.group(1))
    elif "429" in error_str or "rate_limit" in error_str or "resource_exhausted" in error_str:
        # Rate limits: longer backoff (30s, 60s, 120s)
        base_delay = 30.0 * (2 ** min(attempt, 3))
    elif any(e in error_str for e in ["timeout", "timed out", "connection", "502", "503"]):
        # Transient errors: shorter backoff
        base_delay = 5.0 * (2 ** attempt)
    else:
        base_delay = 10.0 * (2 ** attempt)

    return min(base_delay, 120.0)


class FixState(TypedDict, total=False):
    impact: dict
    file_path: str
    file_content: str
    patch: PatchSuggestion | None
    patched_content: str | None
    error: str | None
    attempts: int
    language: str
    vendor_guidance: str | None
    new_spec_context: str | None
    # Guardrail fields
    patch_history: list[str]
    error_history: list[str]
    fix_errors: list[dict]


class SuggestionModel:
    def __init__(
        self,
        api_key: str,
        model_name: str = "gpt-4o-mini",
        base_url: str | None = None,
        fallback_api_key: str | None = None,
        fallback_model: str | None = None,
        fallback_base_url: str | None = None,
        timeout_seconds: int = 60,
    ):
        if not api_key:
            raise ValueError("an API key is required to build a SuggestionModel")
        self._api_key = api_key
        self._model_name = model_name
        self._base_url = base_url
        self._fallback_api_key = fallback_api_key
        self._fallback_model = fallback_model
        self._fallback_base_url = fallback_base_url
        self._timeout_seconds = timeout_seconds
        self._llm = None
        self._fallback = None
        self.cost_tracker = CostTracker()

    def _get_llm(self):
        if self._llm is None:
            from langchain_openai import ChatOpenAI

            kwargs = {
                "model": self._model_name,
                "api_key": self._api_key,
                "temperature": 0,
                "max_tokens": 1024,
                "request_timeout": self._timeout_seconds,
            }
            if self._base_url:
                kwargs["base_url"] = self._base_url
            self._llm = ChatOpenAI(**kwargs).with_structured_output(PatchSuggestion)
        return self._llm

    def _get_fallback(self):
        if self._fallback is None and self._fallback_api_key:
            from langchain_openai import ChatOpenAI

            fkwargs = {
                "model": self._fallback_model,
                "api_key": self._fallback_api_key,
                "temperature": 0,
                "max_tokens": 1024,
                "request_timeout": self._timeout_seconds,
            }
            if self._fallback_base_url:
                fkwargs["base_url"] = self._fallback_base_url
            self._fallback = ChatOpenAI(**fkwargs).with_structured_output(PatchSuggestion)
        return self._fallback

    def _extract_usage(self, result, model: str) -> None:
        """Extract real token counts from LangChain response and record them."""
        input_tokens = 0
        output_tokens = 0
        meta = getattr(result, "response_metadata", {}) or {}
        usage = meta.get("token_usage", {}) or meta.get("usage", {}) or {}
        if usage:
            input_tokens = usage.get("prompt_tokens", 0) or usage.get("input_tokens", 0) or 0
            output_tokens = usage.get("completion_tokens", 0) or usage.get("output_tokens", 0) or 0
        else:
            usage_meta = getattr(result, "usage_metadata", None)
            if usage_meta:
                input_tokens = getattr(usage_meta, "input_tokens", 0) or 0
                output_tokens = getattr(usage_meta, "output_tokens", 0) or 0
        self.cost_tracker.record(input_tokens, output_tokens, model)

    def suggest(self, prompt: str) -> PatchSuggestion:
        """Call LLM with retry, fallback, and timeout."""
        max_retries = 3
        last_exc: Exception | None = None

        # Try primary model
        for attempt in range(max_retries):
            try:
                result = self._get_llm().invoke(prompt)
                self._extract_usage(result, self._model_name)
                return result
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                classified = classify_error(exc, attempt)
                if not classified.retryable:
                    break
                delay = _retry_delay(exc, attempt)
                if delay > 0:
                    time.sleep(delay)

        # Try fallback model
        fallback = self._get_fallback()
        if fallback is None:
            raise last_exc or RuntimeError("primary LLM failed")

        for attempt in range(max_retries):
            try:
                result = fallback.invoke(prompt)
                self._extract_usage(result, self._fallback_model)
                return result
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                classified = classify_error(exc, attempt)
                if not classified.retryable:
                    break
                delay = _retry_delay(exc, attempt)
                if delay > 0:
                    time.sleep(delay)

        raise last_exc or RuntimeError("fallback LLM failed")


def build_suggestion_model(
    settings: Settings, vendor_slug: str | None = None
) -> SuggestionModel:
    model_name = settings.llm_model
    if vendor_slug:
        try:
            from app.registry.vendors import get_vendor

            vendor = get_vendor(settings, vendor_slug)
            if vendor.fix_model:
                model_name = vendor.fix_model
        except ValueError:
            pass
    api_key = settings.gemini_api_key or settings.openai_api_key
    return SuggestionModel(
        api_key=api_key,
        model_name=model_name,
        base_url=settings.llm_base_url,
        fallback_api_key=settings.openrouter_api_key,
        fallback_model=settings.openrouter_model or "nvidia/nemotron-3-ultra-550b-a55b:free",
        fallback_base_url="https://openrouter.ai/api/v1",
        timeout_seconds=getattr(settings, "llm_timeout_seconds", 60),
    )


def build_fix_graph(
    suggestion_model,
    max_attempts: int = 3,
    base_url: str | None = None,
    token_budget: TokenBudget | None = None,
):
    """Build the LangGraph fix graph with guardrails."""
    validator = PatchValidator()
    budget = token_budget or TokenBudget()

    def generate(state: FixState) -> dict:
        impact = state["impact"]

        # Truncate content to fit token budget
        content = state["file_content"]
        truncated = budget.truncate_to_budget(
            content,
            impact["line"],
            radius=5,
        )

        # If content wasn't truncated, use numbered_context for line numbers
        if truncated == content:
            truncated = numbered_context(content, impact["line"], radius=5)

        prompt = build_prompt(
            impact,
            state["file_path"],
            truncated,
            state.get("error"),
            language=state.get("language", "py"),
            vendor_guidance=state.get("vendor_guidance"),
            new_spec_context=state.get("new_spec_context"),
        )

        # Check if prompt fits in budget
        if not budget.fits_in_budget(prompt):
            return {
                "error": f"prompt exceeds token budget ({budget.estimate_tokens(prompt)} tokens)",
                "attempts": state.get("attempts", 0) + 1,
            }

        # Let LLM errors propagate to _invoke_graph for proper crash handling
        patch = suggestion_model.suggest(prompt)
        return {
            "patch": patch,
            "attempts": state.get("attempts", 0) + 1,
        }

    def apply(state: FixState) -> dict:
        if state.get("patch") is None:
            return {}
        content, err = apply_patch(state["file_content"], state["patch"])
        return {"patched_content": content, "error": err}

    def validate(state: FixState) -> dict:
        if state.get("patched_content") is None:
            return {}

        # 1. Syntax validation
        err = validate_source(state["patched_content"], state.get("language", "py"))
        if err:
            return {"error": err}

        # 2. Semantic guard - still calls removed endpoint?
        err = _still_calls_error(
            state["patched_content"],
            state["impact"],
            base_url,
            state.get("language", "py"),
        )
        if err:
            return {"error": err}

        # 3. General semantic guards from registry
        from app.fix.semantic_guards import run_semantic_guard

        err = run_semantic_guard(state["patched_content"], state["impact"])
        if err:
            return {"error": err}

        # 4. Patch validation - line number, file path, diff
        if state.get("patch") and state.get("impact"):
            patch_errors = validator.validate(
                state["patch"],
                state["file_content"],
                state["impact"],
            )
            if patch_errors:
                return {"error": f"patch validation failed: {'; '.join(patch_errors)}"}

        return {"error": None}

    def route(state: FixState) -> str:
        # Successful patch
        if state.get("error") is None:
            return "done"

        # Max attempts reached
        if state.get("attempts", 0) >= max_attempts:
            return "give_up"

        # Duplicate patch detection
        current_patch = _patch_signature(state.get("patch"))
        patch_history = state.get("patch_history", [])
        if current_patch and current_patch in patch_history:
            return "give_up"

        # No progress detection (same error twice)
        error_history = state.get("error_history", [])
        current_error = state.get("error")
        if len(error_history) >= 2 and error_history[-1] == error_history[-2] == current_error:
            return "give_up"

        # Terminal error types
        error_str = state.get("error", "")
        if any(term in error_str for term in ["token budget", "token limit", "context_length"]):
            return "give_up"

        return "retry"

    graph = StateGraph(FixState)
    graph.add_node("generate", generate)
    graph.add_node("apply", apply)
    graph.add_node("validate", validate)
    graph.add_edge(START, "generate")
    graph.add_edge("generate", "apply")
    graph.add_edge("apply", "validate")
    graph.add_conditional_edges(
        "validate",
        route,
        {"retry": "generate", "done": END, "give_up": END},
    )
    return graph.compile()


def _patch_signature(patch: PatchSuggestion | None) -> str | None:
    if patch is None:
        return None
    return json.dumps(
        {"file": patch.file, "line": patch.line, "end_line": patch.end_line,
         "action": patch.action, "replacement": patch.replacement, "content": patch.content},
        sort_keys=True,
    )


def numbered_context(content: str, line: int, radius: int = 3) -> str:
    lines = content.splitlines()
    start = max(0, line - 1 - radius)
    end = min(len(lines), line - 1 + radius + 1)
    return "\n".join(f"{i + 1}: {lines[i]}" for i in range(start, end))


def impact_to_dict(impact) -> dict:
    return {
        "file": impact.usage.file,
        "line": impact.usage.line,
        "method": impact.usage.method,
        "path": impact.usage.path,
        "change_kind": impact.change.kind,
        "change_severity": impact.change.severity,
        "change_path": impact.change.path,
        "change_detail": impact.change.detail,
        "language": language_for_file(impact.usage.file),
    }


def _still_calls_error(
    content: str,
    impact: dict,
    base_url: str | None,
    language: str = "py",
) -> str | None:
    if base_url is None or impact.get("change_kind") != "endpoint_removed":
        return None
    usages, _headers, _bodies, _auths, _responses = ApiScanner(base_url=base_url).scan_source(
        content, filename="patched", language=language
    )
    for usage in usages:
        if usage.method == impact["method"] and match_path(usage.path, impact["change_path"]):
            return (
                f"patch still calls removed endpoint "
                f"{usage.method.upper()} {impact['change_path']}"
            )
    return None


def _invoke_graph(graph, state: dict) -> dict:
    try:
        result = graph.invoke(state)
        # Track patch/error history for duplicate detection
        patch_history = list(result.get("patch_history", []))
        error_history = list(result.get("error_history", []))

        if result.get("patch"):
            sig = _patch_signature(result["patch"])
            if sig:
                patch_history.append(sig)

        if result.get("error"):
            error_history.append(result["error"])

        result["patch_history"] = patch_history
        result["error_history"] = error_history
        return result
    except Exception as exc:  # noqa: BLE001
        return {"error": f"fix agent crashed: {type(exc).__name__}: {str(exc)[:500]}", "patched_content": None}


_GRAPH_MODEL_COUNTER: int = 0


def _get_or_build_graph(suggestion_model, max_attempts: int, base_url: str | None, cache: dict):
    global _GRAPH_MODEL_COUNTER
    # Use a unique counter to avoid id() reuse after garbage collection
    if not hasattr(suggestion_model, "_graph_cache_id"):
        _GRAPH_MODEL_COUNTER += 1
        suggestion_model._graph_cache_id = _GRAPH_MODEL_COUNTER
    key = (suggestion_model._graph_cache_id, max_attempts, base_url)
    if key not in cache:
        cache[key] = build_fix_graph(suggestion_model, max_attempts, base_url)
    return cache[key]


_GRAPH_CACHE: dict[tuple, object] = {}


def fix_impact_on_content(
    impact,
    file_path: str,
    content: str,
    suggestion_model,
    previous_error: str | None = None,
    max_attempts: int = 3,
    base_url: str | None = None,
    vendor_guidance: str | None = None,
    new_spec_context: str | None = None,
) -> tuple[str | None, str | None]:
    graph = _get_or_build_graph(suggestion_model, max_attempts, base_url, _GRAPH_CACHE)
    final = _invoke_graph(
        graph,
        {
            "impact": impact_to_dict(impact),
            "file_path": file_path,
            "file_content": content,
            "error": previous_error,
            "attempts": 0,
            "language": language_for_file(file_path),
            "vendor_guidance": vendor_guidance,
            "new_spec_context": new_spec_context,
            "patch_history": [],
            "error_history": [],
        },
    )
    success = final.get("error") is None and final.get("patched_content") is not None
    return (final.get("patched_content"), None) if success else (None, final.get("error"))


def run_fix(
    impacts,
    suggestion_model,
    max_attempts: int = 3,
    base_url: str | None = None,
    vendor_guidance: str | None = None,
    new_spec_context: str | None = None,
) -> list[FixResult]:
    from app.fix.strategies import get_strategy

    graph = _get_or_build_graph(suggestion_model, max_attempts, base_url, _GRAPH_CACHE)
    contents: dict[str, str] = {}
    results: list[FixResult] = []
    for impact in impacts:
        change_kind = impact.change.kind.value if hasattr(impact.change.kind, 'value') else str(impact.change.kind)

        # Skip informational changes (no fix needed)
        strategy = get_strategy(change_kind)
        if strategy and not strategy.llm_required and not strategy.pattern:
            results.append(
                FixResult(
                    file=impact.usage.file,
                    line=impact.usage.line,
                    success=True,
                    change_kind=change_kind,
                )
            )
            continue

        path = Path(impact.usage.file)
        if path not in contents:
            contents[path] = path.read_text(encoding="utf-8-sig")
        final = _invoke_graph(
            graph,
            {
                "impact": impact_to_dict(impact),
                "file_path": impact.usage.file,
                "file_content": contents[path],
                "error": None,
                "attempts": 0,
                "language": language_for_file(impact.usage.file),
                "vendor_guidance": vendor_guidance,
                "new_spec_context": new_spec_context,
                "patch_history": [],
                "error_history": [],
            },
        )
        success = final.get("error") is None and final.get("patched_content") is not None
        results.append(
            FixResult(
                file=impact.usage.file,
                line=impact.usage.line,
                success=success,
                patch=final.get("patch"),
                error=final.get("error"),
                change_kind=change_kind,
            )
        )
        if success:
            contents[path] = final["patched_content"]
            path.write_text(final["patched_content"], encoding="utf-8")
    return results
