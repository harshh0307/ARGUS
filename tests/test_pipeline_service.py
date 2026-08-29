
from types import SimpleNamespace

from app.detection.models import BREAKING, Change
from app.github.pr import PRLoopResult
from app.scan.models import Impact, Usage
from app.services import pipeline


def usage(file="app.py", line=6, method="get", path="/repos/x/tags/protection"):
    return Usage(file, line, method, path)


def change(
    kind="endpoint_removed",
    path="/repos/{owner}/{repo}/tags/protection",
    method="delete",
    severity=BREAKING,
    detail="endpoint was removed",
):
    return Change(kind, severity, path, method, detail)


def impact(file="app.py", line=6):
    return Impact(usage(file, line), change())


class FakeScanner:
    def __init__(self, usages):
        self.usages = usages

    def scan(self, root):
        return self.usages


def settings(**overrides):
    defaults = {
        "github_token": "token",
        "api_base_url": "https://api.github.com",
        "fix_max_attempts": 3,
        "generated_at": None,
    }
    defaults["llm_model"] = "m"
    defaults["llm_base_url"] = None
    defaults["gemini_api_key"] = None
    defaults["openai_api_key"] = "k"
    defaults["openrouter_api_key"] = None
    defaults["openrouter_model"] = None
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_fix_directory_dry_run_returns_steps(monkeypatch, tmp_path):
    target = tmp_path / "app.py"
    target.write_text("import requests\nresp = requests.get('/repos/x/tags/protection')\n")

    def fake_detect(s, **kw):
        return {"changes": [change()]}

    monkeypatch.setattr(pipeline, "run_detection", fake_detect)
    monkeypatch.setattr(pipeline, "ApiScanner", lambda **kw: FakeScanner([usage()]))
    monkeypatch.setattr(pipeline, "assess_impact", lambda usages, changes: [impact()])
    monkeypatch.setattr(
        pipeline,
        "fix_impact_on_content",
        lambda *a, **k: ("import requests\nresp = []\n", None),
    )
    monkeypatch.setattr(pipeline, "build_suggestion_model", lambda s, vendor_slug=None: object())

    outcome = pipeline.fix_directory(settings(), tmp_path, dry_run=True)

    assert outcome.had_impacts
    assert len(outcome.steps) == 1
    step = outcome.steps[0]
    assert step["ok"] is True
    assert step["after"] == "import requests\nresp = []\n"
    assert target.read_text().startswith("import requests\nresp = requests.get")


def test_fix_directory_no_impacts_returns_empty(monkeypatch, tmp_path):
    (tmp_path / "app.py").write_text("import requests\n")

    def fake_detect(s, **kw):
        return {"changes": [change()]}

    monkeypatch.setattr(pipeline, "run_detection", fake_detect)
    monkeypatch.setattr(pipeline, "ApiScanner", lambda **kw: FakeScanner([]))
    monkeypatch.setattr(pipeline, "assess_impact", lambda usages, changes: [])

    outcome = pipeline.fix_directory(settings(), tmp_path)

    assert not outcome.had_impacts
    assert outcome.steps == []


class FakeGitHubClient:
    def __init__(self, *args, **kwargs):
        self.calls = []

    def get_repo_info(self, owner, repo):
        return {"default_branch": "main"}

    def find_open_pull(self, owner, repo, branch):
        return None

    def get_ref(self, owner, repo, branch):
        return None

    def merge_pull_request(self, owner, repo, number, merge_method="squash"):
        self.calls.append(("merge", owner, repo, number, merge_method))

    def delete_branch(self, owner, repo, branch):
        self.calls.append(("delete_branch", owner, repo, branch))


def test_run_repo_pipeline_delegates_to_pr_loop(monkeypatch, tmp_path):
    (tmp_path / "app.py").write_text("import requests\nresp = requests.get('/repos/x/tags/protection')\n")
    fake_client = FakeGitHubClient()
    captured = {}

    def fake_detect(s, **kw):
        return {"changes": [change()]}

    def fake_pr_loop(client, owner, repo, **kwargs):
        captured["owner"] = owner
        captured["repo"] = repo
        captured["base"] = kwargs["base"]
        captured["branch"] = kwargs["branch"]
        captured["files"] = kwargs["files"]
        return PRLoopResult(7, "https://github.com/x/y/pull/7", passed=True, attempts=2)

    monkeypatch.setattr(pipeline, "run_detection", fake_detect)
    monkeypatch.setattr(pipeline, "ApiScanner", lambda **kw: FakeScanner([usage()]))
    monkeypatch.setattr(pipeline, "assess_impact", lambda usages, changes: [impact()])
    monkeypatch.setattr(pipeline, "GitHubClient", lambda token: fake_client)
    monkeypatch.setattr(pipeline, "build_suggestion_model", lambda s, vendor_slug=None: object())
    monkeypatch.setattr(pipeline, "run_pr_loop", fake_pr_loop)

    outcome = pipeline.run_repo_pipeline(
        settings(),
        "o",
        "r",
        local_dir=tmp_path,
        merge=False,
    )

    assert outcome.pr_result.passed is True
    assert captured["owner"] == "o"
    assert captured["repo"] == "r"
    assert captured["base"] == "main"
    assert captured["branch"] == "argus/fix"
    assert "app.py" in captured["files"]
    assert fake_client.calls == []


def test_run_repo_pipeline_merge_on_green(monkeypatch, tmp_path):
    (tmp_path / "app.py").write_text("import requests\nresp = requests.get('/repos/x/tags/protection')\n")
    fake_client = FakeGitHubClient()

    def fake_detect(s, **kw):
        return {"changes": [change()]}

    def fake_pr_loop(client, owner, repo, **kwargs):
        return PRLoopResult(7, "https://github.com/x/y/pull/7", passed=True, attempts=1)

    monkeypatch.setattr(pipeline, "run_detection", fake_detect)
    monkeypatch.setattr(pipeline, "ApiScanner", lambda **kw: FakeScanner([usage()]))
    monkeypatch.setattr(pipeline, "assess_impact", lambda usages, changes: [impact()])
    monkeypatch.setattr(pipeline, "GitHubClient", lambda token: fake_client)
    monkeypatch.setattr(pipeline, "build_suggestion_model", lambda s, vendor_slug=None: object())
    monkeypatch.setattr(pipeline, "run_pr_loop", fake_pr_loop)

    outcome = pipeline.run_repo_pipeline(settings(), "o", "r", local_dir=tmp_path)

    assert outcome.merged is False
    assert outcome.merge_error is None
    assert outcome.pr_result.passed is True
    assert ("merge", "o", "r", 7, "squash") not in fake_client.calls
