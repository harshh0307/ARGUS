from __future__ import annotations

import re
import time
from pathlib import Path
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.core.config import Settings
from app.fix.models import FixResult, PatchSuggestion
from app.fix.patch import apply_patch, validate_python
from app.fix.prompt import build_prompt
from app.scan.impact import match_path
from app.scan.scanner import ApiScanner

RETRY_DELAY_RE = re.compile(r"retry in ([\d.]+)s")


def _retry_delay(exc: Exception, attempt: int) -> float:
    match = RETRY_DELAY_RE.search(str(exc))
    if match:
        return min(float(match.group(1)) + 1.0, 60.0)
    return min(10.0 * (2**attempt), 60.0)


class FixState(TypedDict, total=False):
    impact: dict
    file_path: str
    file_content: str
    patch: PatchSuggestion | None
    patched_content: str | None
    error: str | None
    attempts: int


class SuggestionModel:
    def __init__(
        self,
        api_key: str,
        model_name: str = "gpt-4o-mini",
        base_url: str | None = None,
        fallback_api_key: str | None = None,
        fallback_model: str | None = None,
        fallback_base_url: str | None = None,
    ):
        if not api_key:
            raise ValueError("an API key is required to build a SuggestionModel")
        self._api_key = api_key
        self._model_name = model_name
        self._base_url = base_url
        self._fallback_api_key = fallback_api_key
        self._fallback_model = fallback_model
        self._fallback_base_url = fallback_base_url
        self._llm = None
        self._fallback = None

    def _get_llm(self):
        if self._llm is None:
            from langchain_openai import ChatOpenAI
            kwargs = {"model": self._model_name, "api_key": self._api_key, "temperature": 0}
            if self._base_url:
                kwargs["base_url"] = self._base_url
            self._llm = ChatOpenAI(**kwargs).with_structured_output(PatchSuggestion)
        return self._llm

    def _get_fallback(self):
        if self._fallback is None and self._fallback_api_key:
            from langchain_openai import ChatOpenAI
            fkwargs = {"model": self._fallback_model, "api_key": self._fallback_api_key, "temperature": 0}
            if self._fallback_base_url:
                fkwargs["base_url"] = self._fallback_base_url
            self._fallback = ChatOpenAI(**fkwargs).with_structured_output(PatchSuggestion)
        return self._fallback

    def suggest(self, prompt: str) -> PatchSuggestion:
        max_retries = 3
        last_exc: Exception | None = None
        for attempt in range(max_retries):
            try:
                return self._get_llm().invoke(prompt)
            except Exception as exc:  # noqa: BLE001 - provider errors are unpredictable
                last_exc = exc
                if "429" not in str(exc):
                    break
                time.sleep(_retry_delay(exc, attempt))
        fallback = self._get_fallback()
        if fallback is None:
            raise last_exc or RuntimeError("primary LLM failed")
        for attempt in range(max_retries):
            try:
                return fallback.invoke(prompt)
            except Exception as exc:  # noqa: BLE001 - provider errors are unpredictable
                last_exc = exc
                time.sleep(_retry_delay(exc, attempt))
        raise last_exc or RuntimeError("fallback LLM failed")


def build_suggestion_model(settings: Settings) -> SuggestionModel:
    api_key = settings.gemini_api_key or settings.openai_api_key
    return SuggestionModel(
        api_key=api_key,
        model_name=settings.llm_model,
        base_url=settings.llm_base_url,
        fallback_api_key=settings.openrouter_api_key,
        fallback_model=settings.openrouter_model or "nvidia/nemotron-3-ultra-550b-a55b:free",
        fallback_base_url="https://openrouter.ai/api/v1",
    )


def build_fix_graph(suggestion_model, max_attempts: int = 3, base_url: str | None = None):
    def generate(state: FixState) -> dict:
        impact = state["impact"]
        context = numbered_context(state["file_content"], impact["line"])
        prompt = build_prompt(impact, state["file_path"], context, state.get("error"))
        return {
            "patch": suggestion_model.suggest(prompt),
            "attempts": state.get("attempts", 0) + 1,
        }

    def apply(state: FixState) -> dict:
        content, err = apply_patch(state["file_content"], state["patch"])
        return {"patched_content": content, "error": err}

    def validate(state: FixState) -> dict:
        if state.get("patched_content") is None:
            return {}
        err = validate_python(state["patched_content"])
        if err is None:
            err = _still_calls_error(state["patched_content"], state["impact"], base_url)
        return {"error": err}

    def route(state: FixState) -> str:
        if state.get("error") is None:
            return "done"
        if state.get("attempts", 0) >= max_attempts:
            return "give_up"
        return "retry"

    graph = StateGraph(FixState)
    graph.add_node("generate", generate)
    graph.add_node("apply", apply)
    graph.add_node("validate", validate)
    graph.add_edge(START, "generate")
    graph.add_edge("generate", "apply")
    graph.add_edge("apply", "validate")
    graph.add_conditional_edges("validate", route, {"retry": "generate", "done": END, "give_up": END})
    return graph.compile()


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
    }


def _still_calls_error(content: str, impact: dict, base_url: str | None) -> str | None:
    if base_url is None or impact.get("change_kind") != "endpoint_removed":
        return None
    usages = ApiScanner(base_url=base_url).scan_source(content, filename="patched")
    for usage in usages:
        if usage.method == impact["method"] and match_path(usage.path, impact["change_path"]):
            return (
                f"patch still calls removed endpoint "
                f"{usage.method.upper()} {impact['change_path']}"
            )
    return None


def _invoke_graph(graph, state: dict) -> dict:
    try:
        return graph.invoke(state)
    except Exception as exc:  # noqa: BLE001 - any LLM/graph failure must degrade cleanly
        return {"error": f"fix agent crashed: {type(exc).__name__}: {str(exc)[:500]}", "patched_content": None}


def _get_or_build_graph(suggestion_model, max_attempts: int, base_url: str | None, cache: dict):
    key = (id(suggestion_model), max_attempts, base_url)
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
        },
    )
    success = final.get("error") is None and final.get("patched_content") is not None
    return (final.get("patched_content"), None) if success else (None, final.get("error"))


def run_fix(impacts, suggestion_model, max_attempts: int = 3, base_url: str | None = None) -> list[FixResult]:
    graph = _get_or_build_graph(suggestion_model, max_attempts, base_url, _GRAPH_CACHE)
    contents: dict[str, str] = {}
    results: list[FixResult] = []
    for impact in impacts:
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
            )
        )
        if success:
            contents[path] = final["patched_content"]
            path.write_text(final["patched_content"], encoding="utf-8")
    return results
