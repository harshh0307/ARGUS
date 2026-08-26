from __future__ import annotations

import io
import tarfile
from types import SimpleNamespace

from app import cli
from app.detection.models import BREAKING, Change
from app.fix.models import FixResult, PatchSuggestion
from app.github.client import GitHubApiError
from app.github.pr import PRLoopResult
from app.scan.models import Impact, Usage
from app.services import pipeline as svc


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


def settings(**overrides):
    defaults = {
        "github_token": "token",
        "api_base_url": "https://api.github.com",
        "fix_max_attempts": 3,
        "llm_model": "m",
        "llm_base_url": None,
        "gemini_api_key": None,
        "openai_api_key": "k",
        "openrouter_api_key": None,
        "openrouter_model": None,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def patch_deps(monkeypatch, **deps):
    for name, value in deps.items():
        monkeypatch.setattr(svc, name, value)


class FakeScanner:
    def __init__(self, usages):
        self.usages = usages

    def scan(self, root):
        return self.usages


def test_parser_has_all_commands():
    parser = cli.build_parser()
    for name in ("detect", "scan", "fix", "pr"):
        assert name in parser._subparsers._group_actions[0].choices


def test_detect_prints_summary(monkeypatch, capsys):
    def fake_detection(settings, **kw):
        return {
            "breaking_count": 1,
            "additive_count": 2,
            "changes": [change(), change(kind="schema_added", method="get", severity="additive")],
        }

    patch_deps(monkeypatch, run_detection=fake_detection)
    assert cli.cmd_detect(SimpleNamespace()) == 0
    out = capsys.readouterr().out
    assert "1 breaking, 1 additive" in out
    assert "endpoint_removed" in out
    assert "DELETE /repos/{owner}/{repo}/tags/protection" in out


def test_scan_reports_no_impacts(monkeypatch, capsys):
    patch_deps(
        monkeypatch,
        run_detection=lambda s, **kw: {"changes": [change()]},
        ApiScanner=lambda **kw: FakeScanner([]),
        assess_impact=lambda usages, changes: [],
    )
    assert cli.cmd_scan(SimpleNamespace(dir=".")) == 0
    assert "0 impacted" in capsys.readouterr().out


def test_scan_reports_impacts(monkeypatch, capsys):
    patch_deps(
        monkeypatch,
        run_detection=lambda s, **kw: {"changes": [change()]},
        ApiScanner=lambda **kw: FakeScanner([usage()]),
        assess_impact=lambda usages, changes: [impact()],
    )
    assert cli.cmd_scan(SimpleNamespace(dir=".")) == 0
    assert "1 impacted" in capsys.readouterr().out


def test_fix_dry_run_prints_diff(monkeypatch, tmp_path, capsys):
    target = tmp_path / "app.py"
    target.write_text("import requests\nresp = requests.get('/repos/x/tags/protection')\n")
    patch_deps(
        monkeypatch,
        run_detection=lambda s, **kw: {"changes": [change()]},
        ApiScanner=lambda **kw: FakeScanner([usage()]),
        assess_impact=lambda usages, changes: [impact()],
        build_suggestion_model=lambda s, vendor_slug=None: object(),
        fix_impact_on_content=lambda *a, **k: ("import requests\nresp = []\n", None),
    )
    args = SimpleNamespace(dir=str(tmp_path), dry_run=True, max_attempts=None)
    assert cli.cmd_fix(args) == 0
    out = capsys.readouterr().out
    assert "OK" in out
    assert "requests.get('/repos/x/tags/protection')" in out
    assert target.read_text().startswith("import requests\nresp = requests.get")
    assert "1/1 fixed for github (dry run)" in out


def test_fix_applies_in_directory(monkeypatch, tmp_path):
    target = tmp_path / "app.py"
    target.write_text("old")
    captured = {}

    def fake_run_fix(impacts, model, max_attempts, base_url=None, vendor_guidance=None):
        captured["impacts"] = impacts
        captured["model"] = model
        captured["max_attempts"] = max_attempts
        captured["base_url"] = base_url
        return [FixResult("app.py", 6, True, PatchSuggestion(file="app.py", line=6, replacement="new"))]

    patch_deps(
        monkeypatch,
        run_detection=lambda s, **kw: {"changes": [change()]},
        ApiScanner=lambda **kw: FakeScanner([usage()]),
        assess_impact=lambda usages, changes: [impact()],
        build_suggestion_model=lambda s, vendor_slug=None: object(),
        run_fix=fake_run_fix,
    )
    args = SimpleNamespace(dir=str(tmp_path), dry_run=False, max_attempts=5)
    assert cli.cmd_fix(args) == 0
    assert captured["max_attempts"] == 5
    assert "1/1 fixed" in captured or captured["impacts"]


def test_fix_missing_key_returns_2(monkeypatch, tmp_path, capsys):
    patch_deps(
        monkeypatch,
        run_detection=lambda s, **kw: {"changes": [change()]},
        ApiScanner=lambda **kw: FakeScanner([usage()]),
        assess_impact=lambda usages, changes: [impact()],
        build_suggestion_model=lambda s, vendor_slug=None: (_ for _ in ()).throw(ValueError("no key")),
    )
    args = SimpleNamespace(dir=str(tmp_path), dry_run=True, max_attempts=None)
    assert cli.cmd_fix(args) == 2
    assert "no key" in capsys.readouterr().err


def test_extract_tarball_strips_root_component(tmp_path):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, is_dir in (
            ("repo-main-abc/", True),
            ("repo-main-abc/app.py", False),
            ("repo-main-abc/README.md", False),
        ):
            data = b"" if is_dir else (b"x" if name.endswith(".py") else b"readme")
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.type = tarfile.DIRTYPE if is_dir else tarfile.REGTYPE
            tar.addfile(info, io.BytesIO(data))
    dest = tmp_path / "out"
    svc._extract_tarball(buf.getvalue(), dest)
    assert (dest / "app.py").read_bytes() == b"x"
    assert (dest / "README.md").read_bytes() == b"readme"


class FakeGitHubClient:
    def __init__(self, *args, **kwargs):
        self.calls = []

    def get_repo_info(self, owner, repo):
        return {"default_branch": "main"}

    def repo_tarball(self, owner, repo, ref=None):
        raise AssertionError("tarball should not be fetched when --dir is used")

    def find_open_pull(self, owner, repo, branch):
        return None

    def get_ref(self, owner, repo, branch):
        return None

    def merge_pull_request(self, owner, repo, number, merge_method="squash"):
        self.calls.append(("merge", owner, repo, number, merge_method))

    def delete_branch(self, owner, repo, branch):
        self.calls.append(("delete_branch", owner, repo, branch))


def test_pr_command_runs_full_loop(monkeypatch, tmp_path, capsys):
    (tmp_path / "app.py").write_text("import requests\nresp = requests.get('/repos/x/tags/protection')\n")
    fake_client = FakeGitHubClient()
    captured = {}

    def fake_pr_loop(client, owner, repo, **kwargs):
        captured["owner"] = owner
        captured["repo"] = repo
        captured["base"] = kwargs["base"]
        captured["branch"] = kwargs["branch"]
        captured["files"] = kwargs["files"]
        return PRLoopResult(7, "https://github.com/x/y/pull/7", passed=True, attempts=2)

    patch_deps(
        monkeypatch,
        run_detection=lambda s, **kw: {"changes": [change()]},
        GitHubClient=lambda token: fake_client,
        ApiScanner=lambda **kw: FakeScanner([usage()]),
        assess_impact=lambda usages, changes: [impact()],
        build_suggestion_model=lambda s, vendor_slug=None: object(),
        run_pr_loop=fake_pr_loop,
    )
    args = SimpleNamespace(
        repo="harshh0307/argus-demo-repo",
        dir=str(tmp_path),
        base=None,
        branch="argus/fix",
        max_attempts=None,
        check_timeout=None,
        merge=False,
    )
    assert cli.cmd_pr(args) == 0
    assert captured["owner"] == "harshh0307"
    assert captured["base"] == "main"
    assert captured["branch"] == "argus/fix"
    assert "app.py" in captured["files"]
    out = capsys.readouterr().out
    assert "PR #7" in out
    assert "passed=True" in out
    assert fake_client.calls == []


def test_pr_command_merges_when_passed_and_flag_set(monkeypatch, tmp_path, capsys):
    (tmp_path / "app.py").write_text("import requests\nresp = requests.get('/repos/x/tags/protection')\n")
    fake_client = FakeGitHubClient()

    def fake_pr_loop(client, owner, repo, **kwargs):
        return PRLoopResult(7, "https://github.com/x/y/pull/7", passed=True, attempts=1)

    patch_deps(
        monkeypatch,
        run_detection=lambda s, **kw: {"changes": [change()]},
        GitHubClient=lambda token: fake_client,
        ApiScanner=lambda **kw: FakeScanner([usage()]),
        assess_impact=lambda usages, changes: [impact()],
        build_suggestion_model=lambda s, vendor_slug=None: object(),
        run_pr_loop=fake_pr_loop,
    )
    args = SimpleNamespace(
        repo="o/r",
        dir=str(tmp_path),
        base=None,
        branch="argus/fix",
        max_attempts=None,
        check_timeout=None,
        merge=True,
    )
    assert cli.cmd_pr(args) == 0
    assert ("merge", "o", "r", 7, "squash") in fake_client.calls
    assert ("delete_branch", "o", "r", "argus/fix") in fake_client.calls
    assert "merged; fix branch deleted" in capsys.readouterr().out


def test_pr_command_does_not_merge_when_failed(monkeypatch, tmp_path):
    (tmp_path / "app.py").write_text("import requests\nresp = requests.get('/repos/x/tags/protection')\n")
    fake_client = FakeGitHubClient()

    def fake_pr_loop(client, owner, repo, **kwargs):
        return PRLoopResult(7, "https://github.com/x/y/pull/7", passed=False, attempts=3, failure="boom")

    patch_deps(
        monkeypatch,
        run_detection=lambda s, **kw: {"changes": [change()]},
        GitHubClient=lambda token: fake_client,
        ApiScanner=lambda **kw: FakeScanner([usage()]),
        assess_impact=lambda usages, changes: [impact()],
        build_suggestion_model=lambda s, vendor_slug=None: object(),
        run_pr_loop=fake_pr_loop,
    )
    args = SimpleNamespace(
        repo="o/r",
        dir=str(tmp_path),
        base=None,
        branch="argus/fix",
        max_attempts=None,
        check_timeout=None,
        merge=True,
    )
    assert cli.cmd_pr(args) == 1
    assert fake_client.calls == []


def test_pr_command_merge_rejection_warns(monkeypatch, tmp_path, capsys):
    (tmp_path / "app.py").write_text("import requests\nresp = requests.get('/repos/x/tags/protection')\n")
    fake_client = FakeGitHubClient()
    fake_client.merge_pull_request = lambda *a, **k: (_ for _ in ()).throw(
        GitHubApiError("PUT merge -> 405: protected")
    )

    def fake_pr_loop(client, owner, repo, **kwargs):
        return PRLoopResult(7, "https://github.com/x/y/pull/7", passed=True, attempts=1)

    patch_deps(
        monkeypatch,
        run_detection=lambda s, **kw: {"changes": [change()]},
        GitHubClient=lambda token: fake_client,
        ApiScanner=lambda **kw: FakeScanner([usage()]),
        assess_impact=lambda usages, changes: [impact()],
        build_suggestion_model=lambda s, vendor_slug=None: object(),
        run_pr_loop=fake_pr_loop,
    )
    args = SimpleNamespace(
        repo="o/r",
        dir=str(tmp_path),
        base=None,
        branch="argus/fix",
        max_attempts=None,
        check_timeout=None,
        merge=True,
    )
    assert cli.cmd_pr(args) == 0
    assert "merge rejected" in capsys.readouterr().out


def test_pr_requires_token(monkeypatch, capsys):
    monkeypatch.setattr(cli, "get_settings", lambda: settings(github_token=None))
    args = SimpleNamespace(
        repo="o/r", dir=None, base=None, branch="argus/fix", max_attempts=None, check_timeout=None,
        merge=False,
    )
    assert cli.cmd_pr(args) == 2
    assert "GITHUB_TOKEN" in capsys.readouterr().err


def test_pr_requires_owner_repo_form(monkeypatch, capsys):
    monkeypatch.setattr(cli, "get_settings", lambda: settings())
    args = SimpleNamespace(
        repo="nope", dir=None, base=None, branch="argus/fix", max_attempts=None, check_timeout=None,
        merge=False,
    )
    assert cli.cmd_pr(args) == 2
    assert "OWNER/REPO" in capsys.readouterr().err

