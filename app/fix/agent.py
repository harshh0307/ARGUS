from __future__ import annotations

from pathlib import Path
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.core.config import Settings
from app.fix.models import FixResult, PatchSuggestion
from app.fix.patch import apply_patch, validate_python
from app.fix.prompt import build_prompt


class FixState(TypedDict, total=False):
    impact: dict
    file_path: str
    file_content: str
    patch: PatchSuggestion | None
    patched_content: str | None
    error: str | None
    attempts: int


class SuggestionModel:
    def __init__(self, api_key: str, model_name: str = "gpt-4o-mini", base_url: str | None = None):
        if not api_key:
            raise ValueError("an API key is required to build a SuggestionModel")
        from langchain_openai import ChatOpenAI

        kwargs = {"model": model_name, "api_key": api_key, "temperature": 0}
        if base_url:
            kwargs["base_url"] = base_url
        self._llm = ChatOpenAI(**kwargs).with_structured_output(PatchSuggestion)

    def suggest(self, prompt: str) -> PatchSuggestion:
        return self._llm.invoke(prompt)


def build_suggestion_model(settings: Settings) -> SuggestionModel:
    api_key = settings.gemini_api_key or settings.openai_api_key
    return SuggestionModel(
        api_key=api_key,
        model_name=settings.llm_model,
        base_url=settings.llm_base_url,
    )


def build_fix_graph(suggestion_model, max_attempts: int = 3):
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
        if state.get("error"):
            return {}
        return {"error": validate_python(state["patched_content"])}

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
        "change_detail": impact.change.detail,
    }


def fix_impact_on_content(
    impact,
    file_path: str,
    content: str,
    suggestion_model,
    previous_error: str | None = None,
    max_attempts: int = 3,
) -> tuple[str | None, str | None]:
    graph = build_fix_graph(suggestion_model, max_attempts)
    final = graph.invoke(
        {
            "impact": impact_to_dict(impact),
            "file_path": file_path,
            "file_content": content,
            "error": previous_error,
            "attempts": 0,
        }
    )
    success = final.get("error") is None and final.get("patched_content") is not None
    return (final.get("patched_content"), None) if success else (None, final.get("error"))


def run_fix(impacts, suggestion_model, max_attempts: int = 3) -> list[FixResult]:
    graph = build_fix_graph(suggestion_model, max_attempts)
    contents: dict[str, str] = {}
    results: list[FixResult] = []
    for impact in impacts:
        path = Path(impact.usage.file)
        if path not in contents:
            contents[path] = path.read_text(encoding="utf-8-sig")
        final = graph.invoke(
            {
                "impact": impact_to_dict(impact),
                "file_path": impact.usage.file,
                "file_content": contents[path],
                "error": None,
                "attempts": 0,
            }
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
