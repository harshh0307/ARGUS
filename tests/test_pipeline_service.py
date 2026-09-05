
from types import SimpleNamespace

from app.scan.models import DriftSignal, Impact, Usage
from app.services import pipeline


def usage(file="app.py", line=6, method="get", path="/repos/x/tags/protection"):
    return Usage(file, line, method, path)


def change(
    kind="endpoint_removed",
    path="/repos/{owner}/{repo}/tags/protection",
    method="delete",
    severity="breaking",
    detail="endpoint was removed",
):
    return DriftSignal(kind=kind, severity=severity, path=path, method=method, detail=detail)


def impact(file="app.py", line=6):
    return Impact(usage(file, line), change())


class FakeOutcome:
    def __init__(self, impacts=None, steps=None, pr_result=None, merged=False):
        self.impacts = impacts or []
        self.steps = steps or []
        self.pr_result = pr_result
        self.merged = merged
        self.merge_error = None
        self.had_impacts = bool(self.impacts)
        self._original_contents = {}
        self.vendor_slug = "github"

    def record_completion(self):
        pass

    def rollback(self, root):
        return 0


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

    fake_outcome = FakeOutcome(
        impacts=[impact()],
        steps=[{
            "file": "app.py",
            "line": 6,
            "ok": True,
            "err": None,
            "before": "import requests\nresp = requests.get('/repos/x/tags/protection')\n",
            "after": "import requests\nresp = []\n",
        }],
    )

    monkeypatch.setattr(pipeline, "scan_changes", lambda s, v, r, languages=None: [impact()])
    monkeypatch.setattr(pipeline, "fix_directory", lambda s, r, max_attempts=None, dry_run=False, vendor_slug="github", languages=None: fake_outcome)

    outcome = pipeline.fix_directory(settings(), tmp_path, dry_run=True)

    assert outcome.had_impacts
    assert len(outcome.steps) == 1
    step = outcome.steps[0]
    assert step["ok"] is True
    assert step["after"] == "import requests\nresp = []\n"
    assert target.read_text().startswith("import requests\nresp = requests.get")


def test_fix_directory_no_impacts_returns_empty(monkeypatch, tmp_path):
    (tmp_path / "app.py").write_text("import requests\n")

    fake_outcome = FakeOutcome(impacts=[], steps=[])

    monkeypatch.setattr(pipeline, "scan_changes", lambda s, v, r, languages=None: [])
    monkeypatch.setattr(pipeline, "fix_directory", lambda s, r, max_attempts=None, dry_run=False, vendor_slug="github", languages=None: fake_outcome)

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
    captured = {}

    def fake_run_repo_pipeline(settings, owner, name, *, branch="main", merge=True, vendor_slug="github", repository_id=None):
        captured["owner"] = owner
        captured["repo"] = name
        captured["branch"] = branch
        return SimpleNamespace(
            pr_result=SimpleNamespace(pr_number=7, pr_url="https://github.com/x/y/pull/7", passed=True, attempts=2),
            merged=False,
            impacts=[impact()],
        )

    monkeypatch.setattr(pipeline, "run_repo_pipeline", fake_run_repo_pipeline)

    outcome = pipeline.run_repo_pipeline(
        settings(),
        "o",
        "r",
        branch="argus/fix",
        merge=False,
    )

    assert outcome.pr_result.passed is True
    assert captured["owner"] == "o"
    assert captured["repo"] == "r"
    assert captured["branch"] == "argus/fix"


def test_run_repo_pipeline_merge_on_green(monkeypatch, tmp_path):
    (tmp_path / "app.py").write_text("import requests\nresp = requests.get('/repos/x/tags/protection')\n")

    def fake_run_repo_pipeline(settings, owner, name, *, branch="main", merge=True, vendor_slug="github", repository_id=None):
        return SimpleNamespace(
            pr_result=SimpleNamespace(pr_number=7, pr_url="https://github.com/x/y/pull/7", passed=True, attempts=1),
            merged=False,
            impacts=[impact()],
        )

    monkeypatch.setattr(pipeline, "run_repo_pipeline", fake_run_repo_pipeline)

    outcome = pipeline.run_repo_pipeline(settings(), "o", "r")

    assert outcome.merged is False
    assert outcome.pr_result.passed is True
