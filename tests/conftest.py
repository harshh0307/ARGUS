"""Shared pytest fixtures for Argus test suite."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.detection.models import BREAKING, Change
from app.fix.models import PatchSuggestion
from app.scan.models import Impact, Usage


@pytest.fixture(autouse=True)
def _clear_graph_cache():
    """Clear the LangGraph cache between tests to avoid stale state."""
    from app.fix.agent import _GRAPH_CACHE
    _GRAPH_CACHE.clear()
    yield
    _GRAPH_CACHE.clear()


# ── Settings fixtures ───────────────────────────────────────────────────────


@pytest.fixture
def settings():
    """Create a mock Settings object with sensible defaults."""
    return SimpleNamespace(
        github_token="ghp_test_token_12345",
        api_base_url="https://api.github.com",
        fix_max_attempts=3,
        llm_model="gpt-4o-mini",
        llm_base_url=None,
        gemini_api_key=None,
        openai_api_key="sk-test-key",
        openrouter_api_key=None,
        openrouter_model=None,
        database_url="sqlite:///:memory:",
    )


# ── Data factory fixtures ──────────────────────────────────────────────────


@pytest.fixture
def make_usage():
    """Factory fixture for creating Usage objects."""

    def _make(
        file: str = "app.py",
        line: int = 6,
        method: str = "get",
        path: str = "/repos/{owner}/{repo}",
    ) -> Usage:
        return Usage(file=file, line=line, method=method, path=path)

    return _make


@pytest.fixture
def make_change():
    """Factory fixture for creating Change objects."""

    def _make(
        kind: str = "endpoint_removed",
        severity: str = BREAKING,
        path: str = "/repos/{owner}/{repo}",
        method: str = "get",
        detail: str = "test change",
        old_value=None,
        new_value=None,
    ) -> Change:
        return Change(kind, severity, path, method, detail, old_value=old_value, new_value=new_value)

    return _make


@pytest.fixture
def make_impact():
    """Factory fixture for creating Impact objects."""

    def _make(
        file: str = "app.py",
        line: int = 6,
        method: str = "get",
        path: str = "/repos/{owner}/{repo}",
        change_kind: str = "endpoint_removed",
    ) -> Impact:
        usage = Usage(file=file, line=line, method=method, path=path)
        change = Change(change_kind, BREAKING, path, method, "test change")
        return Impact(usage=usage, change=change)

    return _make


@pytest.fixture
def make_patch():
    """Factory fixture for creating PatchSuggestion objects."""

    def _make(
        file: str = "app.py",
        line: int = 6,
        action: str = "replace",
        replacement: str = "",
        end_line: int | None = None,
        content: str | None = None,
        explanation: str = "",
    ) -> PatchSuggestion:
        return PatchSuggestion(
            file=file,
            line=line,
            action=action,
            replacement=replacement,
            end_line=end_line,
            content=content,
            explanation=explanation,
        )

    return _make


# ── File system fixtures ───────────────────────────────────────────────────


@pytest.fixture
def sample_python_file(tmp_path):
    """Create a sample Python file with API calls."""
    content = '''import requests

BASE_URL = "https://api.github.com"

def get_repos(owner):
    return requests.get(f"{BASE_URL}/users/{owner}/repos")

def create_repo(name, token):
    headers = {"Authorization": f"Bearer {token}"}
    return requests.post(f"{BASE_URL}/user/repos", json={"name": name}, headers=headers)

def delete_repo(owner, repo, token):
    headers = {"Authorization": f"Bearer {token}"}
    return requests.delete(f"{BASE_URL}/repos/{owner}/{repo}", headers=headers)
'''
    file = tmp_path / "app.py"
    file.write_text(content, encoding="utf-8")
    return file


@pytest.fixture
def sample_js_file(tmp_path):
    """Create a sample JavaScript file with API calls."""
    content = '''const BASE_URL = "https://api.github.com";

async function getRepos(owner) {
    const response = await fetch(`${BASE_URL}/users/${owner}/repos`);
    return response.json();
}

async function createRepo(name, token) {
    const response = await fetch(`${BASE_URL}/user/repos`, {
        method: "POST",
        headers: {
            "Authorization": `Bearer ${token}`,
            "Content-Type": "application/json"
        },
        body: JSON.stringify({ name })
    });
    return response.json();
}
'''
    file = tmp_path / "app.js"
    file.write_text(content, encoding="utf-8")
    return file


@pytest.fixture
def sample_go_file(tmp_path):
    """Create a sample Go file with API calls."""
    content = '''package main

import (
    "fmt"
    "net/http"
    "io"
)

const BaseURL = "https://api.github.com"

func getRepos(owner string) (*http.Response, error) {
    return http.Get(fmt.Sprintf("%s/users/%s/repos", BaseURL, owner))
}

func createRepo(name string, token string) (*http.Response, error) {
    req, _ := http.NewRequest("POST", fmt.Sprintf("%s/user/repos", BaseURL), nil)
    req.Header.Set("Authorization", "Bearer "+token)
    return http.DefaultClient.Do(req)
}
'''
    file = tmp_path / "main.go"
    file.write_text(content, encoding="utf-8")
    return file


@pytest.fixture
def sample_multi_lang_project(tmp_path):
    """Create a multi-language project directory."""
    # Python
    py_dir = tmp_path / "python"
    py_dir.mkdir()
    (py_dir / "client.py").write_text(
        'import requests\nrequests.get("https://api.github.com/repos/{owner}/{repo}")\n',
        encoding="utf-8",
    )

    # JavaScript
    js_dir = tmp_path / "javascript"
    js_dir.mkdir()
    (js_dir / "client.js").write_text(
        'fetch("https://api.github.com/repos/{owner}/{repo}")\n',
        encoding="utf-8",
    )

    # Go
    go_dir = tmp_path / "go"
    go_dir.mkdir()
    (go_dir / "client.go").write_text(
        'package main\nimport "net/http"\nhttp.Get("https://api.github.com/repos/{owner}/{repo}")\n',
        encoding="utf-8",
    )

    return tmp_path


# ── Mock GitHub client fixture ──────────────────────────────────────────────


class FakeGitHubClient:
    """In-memory fake GitHub client for integration tests."""

    def __init__(self):
        self.repos = {}
        self.prs = {}
        self.branches = {}
        self.calls = []

    def get_repo_info(self, owner, repo):
        self.calls.append(("get_repo_info", owner, repo))
        return self.repos.get(f"{owner}/{repo}", {"default_branch": "main"})

    def repo_tarball(self, owner, repo, ref):
        self.calls.append(("repo_tarball", owner, repo, ref))
        return b""

    def find_open_pull(self, owner, repo, branch):
        self.calls.append(("find_open_pull", owner, repo, branch))
        return self.prs.get(f"{owner}/{repo}/{branch}")

    def close_pull(self, owner, repo, pr_number):
        self.calls.append(("close_pull", owner, repo, pr_number))

    def get_ref(self, owner, repo, ref):
        self.calls.append(("get_ref", owner, repo, ref))
        return self.branches.get(f"{owner}/{repo}/{ref}")

    def delete_branch(self, owner, repo, branch):
        self.calls.append(("delete_branch", owner, repo, branch))

    def create_pull(self, owner, repo, **kwargs):
        self.calls.append(("create_pull", owner, repo, kwargs))
        pr_number = len(self.prs) + 1
        self.prs[f"{owner}/{repo}/{kwargs.get('head', 'argus/fix')}"] = pr_number
        return pr_number, f"https://github.com/{owner}/{repo}/pull/{pr_number}"

    def merge_pull_request(self, owner, repo, pr_number, merge_method="squash"):
        self.calls.append(("merge_pull_request", owner, repo, pr_number, merge_method))


@pytest.fixture
def fake_github():
    """Create a FakeGitHubClient instance."""
    return FakeGitHubClient()


# ── Mock suggestion model fixture ───────────────────────────────────────────


class FakeSuggestionModel:
    """Fake suggestion model that returns pre-configured patches."""

    def __init__(self, *patches):
        self.patches = list(patches)
        self.calls = 0
        self.prompts = []

    def suggest(self, prompt):
        self.calls += 1
        self.prompts.append(prompt)
        if self.patches:
            return self.patches.pop(0)
        return PatchSuggestion(file="app.py", line=1, action="replace", replacement="")


@pytest.fixture
def fake_suggestion_model():
    """Create a FakeSuggestionModel instance."""
    return FakeSuggestionModel()


@pytest.fixture
def make_suggestion_model():
    """Factory fixture for creating FakeSuggestionModel with specific patches."""

    def _make(*patches):
        return FakeSuggestionModel(*patches)

    return _make
