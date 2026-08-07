import ast

from app.detection.models import BREAKING, Change
from app.fix.agent import fix_impact_on_content, run_fix
from app.fix.models import PatchSuggestion
from app.fix.patch import apply_patch, validate_python
from app.scan.models import Impact, Usage


class FakeSuggestionModel:
    def __init__(self, *suggestions: PatchSuggestion):
        self.suggestions = list(suggestions)
        self.calls = 0
        self.last_prompt = ""

    def suggest(self, prompt: str) -> PatchSuggestion:
        self.calls += 1
        self.last_prompt = prompt
        if self.suggestions:
            return self.suggestions.pop(0)
        return PatchSuggestion(file="", line=1)


def impact(file, line=3, method="get", path="/repos/{owner}/{repo}/tags/protection"):
    return Impact(
        usage=Usage(file=str(file), line=line, method=method, path=path),
        change=Change("endpoint_removed", BREAKING, path, method, "endpoint is no longer documented"),
    )


def test_successful_replace(tmp_path):
    f = tmp_path / "app.py"
    f.write_text('import requests\n\nresp = requests.get("https://api.github.com/repos/me/x/tags/protection")\n')
    model = FakeSuggestionModel(
        PatchSuggestion(
            file=str(f),
            line=3,
            action="replace",
            replacement='resp = requests.get("https://api.github.com/repos/me/x/branches")',
        )
    )
    results = run_fix([impact(f, line=3)], model)
    assert results[0].success
    assert model.calls == 1
    content = f.read_text(encoding="utf-8")
    assert "branches" in content
    assert ast.parse(content) is not None


def test_remove_action_deletes_line(tmp_path):
    f = tmp_path / "app.py"
    f.write_text('import requests\nresp = requests.get("https://api.github.com/repos/me/x/tags/protection")\nprint("done")\n')
    model = FakeSuggestionModel(PatchSuggestion(file=str(f), line=2, action="remove"))
    results = run_fix([impact(f, line=2)], model)
    assert results[0].success
    content = f.read_text(encoding="utf-8")
    assert "tags/protection" not in content
    assert "print" in content


def test_retries_after_bad_suggestion(tmp_path):
    f = tmp_path / "app.py"
    f.write_text('import requests\nresp = requests.get("https://api.github.com/repos/me/x/tags/protection")\n')
    model = FakeSuggestionModel(
        PatchSuggestion(file=str(f), line=2, action="replace", replacement=""),
        PatchSuggestion(
            file=str(f),
            line=2,
            action="replace",
            replacement='resp = requests.get("https://api.github.com/repos/me/x/branches")',
        ),
    )
    results = run_fix([impact(f, line=2)], model)
    assert results[0].success
    assert model.calls == 2
    assert "empty" in model.last_prompt


def test_syntax_error_triggers_retry(tmp_path):
    f = tmp_path / "app.py"
    f.write_text('import requests\nresp = requests.get("https://api.github.com/repos/me/x/tags/protection")\n')
    model = FakeSuggestionModel(
        PatchSuggestion(file=str(f), line=2, action="replace", replacement="def (:"),
        PatchSuggestion(
            file=str(f),
            line=2,
            action="replace",
            replacement='resp = requests.get("https://api.github.com/repos/me/x/branches")',
        ),
    )
    results = run_fix([impact(f, line=2)], model)
    assert results[0].success
    assert model.calls == 2


def test_gives_up_after_max_attempts(tmp_path):
    f = tmp_path / "app.py"
    f.write_text('import requests\nresp = requests.get("https://api.github.com/repos/me/x/tags/protection")\n')
    model = FakeSuggestionModel(
        PatchSuggestion(file=str(f), line=2, action="replace", replacement="def (:"),
        PatchSuggestion(file=str(f), line=2, action="replace", replacement="def (:"),
    )
    results = run_fix([impact(f, line=2)], model, max_attempts=2)
    assert not results[0].success
    assert results[0].error is not None
    assert model.calls == 2
    assert "tags/protection" in f.read_text(encoding="utf-8")


def test_prompt_contains_change_and_context(tmp_path):
    f = tmp_path / "app.py"
    f.write_text('import requests\n\nresp = requests.get("https://api.github.com/repos/me/x/tags/protection")\n')
    model = FakeSuggestionModel(PatchSuggestion(file=str(f), line=3, action="replace", replacement="x = 1"))
    run_fix([impact(f, line=3)], model)
    assert "endpoint is no longer documented" in model.last_prompt
    assert "GET" in model.last_prompt
    assert "3: " in model.last_prompt


def test_apply_patch_preserves_trailing_newline():
    content = "a\nb\nc\n"
    patched, err = apply_patch(content, PatchSuggestion(file="x", line=2, action="replace", replacement="B"))
    assert err is None
    assert patched == "a\nB\nc\n"


def test_apply_patch_line_out_of_range():
    patched, err = apply_patch("a\n", PatchSuggestion(file="x", line=9, action="replace", replacement="B"))
    assert patched is None
    assert "out of range" in err


def test_validate_python_detects_syntax_error():
    assert validate_python("def (:\n") is not None
    assert validate_python("x = 1\n") is None


def test_noop_patch_rejected_when_call_remains():
    echo = PatchSuggestion(
        file="app.py",
        line=6,
        action="replace",
        replacement='    resp = requests.get(f"{BASE}/repos/{owner}/{repo}/tags/protection")',
    )
    model = FakeSuggestionModel(echo, echo, echo)
    content = (
        "import requests\n\n"
        'BASE = "https://api.github.com"\n\n'
        "def protect_tags(owner, repo):\n"
        '    resp = requests.get(f"{BASE}/repos/{owner}/{repo}/tags/protection")\n'
        "    return resp.json()\n"
    )
    fixed, err = fix_impact_on_content(
        impact("app.py", line=6), "app.py", content, model, base_url="https://api.github.com"
    )
    assert fixed is None
    assert "still calls removed endpoint" in err
    assert model.calls == 3


def test_non_endpoint_removed_kind_skips_semantic_check():
    model = FakeSuggestionModel(
        PatchSuggestion(file="app.py", line=2, action="replace", replacement="x = 1")
    )
    change = Change(
        "param_removed", BREAKING, "/repos/{owner}/{repo}/tags/protection", "get", "p removed"
    )
    imp = Impact(Usage("app.py", 2, "get", "/repos/{owner}/{repo}/tags/protection"), change)
    fixed, err = fix_impact_on_content(
        imp, "app.py", "a = 1\nb = 2\n", model, base_url="https://api.github.com"
    )
    assert fixed is not None
    assert err is None


def test_semantic_guard_retries_with_second_suggestion(tmp_path):
    f = tmp_path / "app.py"
    f.write_text('import requests\nresp = requests.get("https://api.github.com/repos/me/x/tags/protection")\n')
    model = FakeSuggestionModel(
        PatchSuggestion(
            file=str(f),
            line=2,
            action="replace",
            replacement='resp = requests.get("https://api.github.com/repos/me/x/tags/protection")',
        ),
        PatchSuggestion(
            file=str(f),
            line=2,
            action="replace",
            replacement='resp = requests.get("https://api.github.com/repos/me/x/branches")',
        ),
    )
    results = run_fix([impact(f, line=2)], model, base_url="https://api.github.com")
    assert results[0].success
    assert model.calls == 2


class CrashingSuggestionModel:
    def suggest(self, prompt):
        raise RuntimeError("provider exploded")


def test_llm_crash_becomes_clean_failure():
    fixed, err = fix_impact_on_content(
        impact("app.py", line=6),
        "app.py",
        "a = 1\nb = 2\n",
        CrashingSuggestionModel(),
        base_url="https://api.github.com",
    )
    assert fixed is None
    assert "fix agent crashed" in err
    assert "RuntimeError" in err
