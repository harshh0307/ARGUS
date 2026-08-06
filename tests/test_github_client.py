import base64
import json

import httpx

from app.github.client import GitHubApiError, GitHubClient
from app.github.models import CheckResult, PullRequest


def make_client(handler):
    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    return GitHubClient(token="test-token", client=client)


def test_branch_head_sha():
    def handler(request):
        return httpx.Response(200, json={"commit": {"sha": "abc123"}})

    client = make_client(handler)
    assert client.branch_head_sha("octo", "demo", "main") == "abc123"


def test_create_branch_payload():
    captured = {}

    def handler(request):
        captured["json"] = json.loads(request.content)
        captured["url"] = str(request.url)
        return httpx.Response(201, json={})

    client = make_client(handler)
    client.create_branch("octo", "demo", "fix-branch", "abc123")
    assert captured["json"] == {"ref": "refs/heads/fix-branch", "sha": "abc123"}
    assert captured["url"].endswith("/repos/octo/demo/git/refs")


def test_get_file_decodes_base64():
    content = "def foo():\n    pass\n"
    payload = {"content": base64.b64encode(content.encode()).decode(), "sha": "sha-1"}

    def handler(request):
        return httpx.Response(200, json=payload)

    client = make_client(handler)
    got = client.get_file("octo", "demo", "app.py", ref="main")
    assert got["content"] == content
    assert got["sha"] == "sha-1"


def test_get_file_missing_returns_none():
    def handler(request):
        return httpx.Response(404, json={"message": "Not Found"})

    client = make_client(handler)
    assert client.get_file("octo", "demo", "nope.py") is None


def test_update_file_payload():
    captured = {}

    def handler(request):
        captured["json"] = json.loads(request.content)
        return httpx.Response(200, json={})

    client = make_client(handler)
    client.update_file("octo", "demo", "app.py", "fix it", 'print("hi")', "sha-1", "branch")
    assert captured["json"]["sha"] == "sha-1"
    assert captured["json"]["branch"] == "branch"
    assert captured["json"]["message"] == "fix it"
    assert base64.b64decode(captured["json"]["content"]).decode() == 'print("hi")'


def test_open_pull_request_parses():
    payload = {"number": 7, "head": {"sha": "head-1"}, "html_url": "https://github.com/o/r/pull/7"}

    def handler(request):
        assert json.loads(request.content)["head"] == "fix"
        return httpx.Response(201, json=payload)

    client = make_client(handler)
    pr = client.open_pull_request("o", "r", "title", "fix", "main", "body")
    assert pr == PullRequest(number=7, head_sha="head-1", html_url="https://github.com/o/r/pull/7")


def test_check_runs_parses():
    payload = {
        "check_runs": [
            {"name": "ci", "status": "completed", "conclusion": "failure"},
            {"name": "lint", "status": "in_progress", "conclusion": None},
        ]
    }

    def handler(request):
        return httpx.Response(200, json=payload)

    client = make_client(handler)
    checks = client.check_runs("o", "r", "head-1")
    assert checks == [
        CheckResult(name="ci", status="completed", conclusion="failure"),
        CheckResult(name="lint", status="in_progress", conclusion=None),
    ]


def test_error_raises_on_server_error():
    def handler(request):
        return httpx.Response(500, text="boom")

    client = make_client(handler)
    try:
        client.branch_head_sha("o", "r", "main")
        assert False, "expected GitHubApiError"
    except GitHubApiError as exc:
        assert "500" in str(exc)


def test_repo_exists():
    def handler(request):
        if str(request.url).endswith("/missing"):
            return httpx.Response(404, json={"message": "Not Found"})
        return httpx.Response(200, json={"full_name": "o/r"})

    client = make_client(handler)
    assert client.repo_exists("o", "r")
    assert not client.repo_exists("o", "missing")


def test_create_repo_payload():
    captured = {}

    def handler(request):
        captured["json"] = json.loads(request.content)
        return httpx.Response(201, json={})

    client = make_client(handler)
    client.create_repo("demo", private=False, description="demo repo")
    assert captured["json"] == {
        "name": "demo",
        "private": False,
        "description": "demo repo",
        "auto_init": True,
    }


def test_delete_repo_sends_delete():
    seen = {}

    def handler(request):
        seen["method"] = request.method
        return httpx.Response(204)

    client = make_client(handler)
    client.delete_repo("o", "r")
    assert seen["method"] == "DELETE"


def test_failure_log_picks_failed_run_and_returns_text():
    calls = []

    def handler(request):
        url = str(request.url)
        calls.append(url)
        if url.endswith("/logs"):
            return httpx.Response(200, text="log line 1\nlog line 2")
        if "/jobs" in url:
            return httpx.Response(200, json={"jobs": [{"id": 10, "name": "check"}]})
        return httpx.Response(
            200,
            json={
                "workflow_runs": [
                    {"id": 1, "conclusion": "success"},
                    {"id": 2, "conclusion": "failure"},
                ]
            },
        )

    client = make_client(handler)
    log = client.failure_log("o", "r", "abc123", "check")
    assert log == "log line 1\nlog line 2"
    assert "status=completed" in calls[0]
    assert "/actions/runs/2/jobs" in calls[1]


def test_find_open_pull_returns_first_number():
    def handler(request):
        return httpx.Response(200, json=[{"number": 9}, {"number": 12}])

    client = make_client(handler)
    assert client.find_open_pull("o", "r", "argus/fix") == 9


def test_find_open_pull_returns_none_when_empty():
    def handler(request):
        return httpx.Response(200, json=[])

    client = make_client(handler)
    assert client.find_open_pull("o", "r", "argus/fix") is None


def test_merge_pull_request_payload():
    captured = {}

    def handler(request):
        captured["method"] = request.method
        captured["json"] = json.loads(request.content)
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"merged": True})

    client = make_client(handler)
    client.merge_pull_request("o", "r", 7)
    assert captured["method"] == "PUT"
    assert captured["json"] == {"merge_method": "squash"}
    assert captured["url"].endswith("/repos/o/r/pulls/7/merge")


def test_merge_pull_request_custom_method():
    captured = {}

    def handler(request):
        captured["json"] = json.loads(request.content)
        return httpx.Response(200, json={"merged": True})

    client = make_client(handler)
    client.merge_pull_request("o", "r", 7, merge_method="rebase")
    assert captured["json"] == {"merge_method": "rebase"}


def test_merge_pull_request_rejected_raises():
    def handler(request):
        return httpx.Response(409, json={"message": "Merge conflict"})

    client = make_client(handler)
    try:
        client.merge_pull_request("o", "r", 7)
        assert False, "expected GitHubApiError"
    except GitHubApiError as exc:
        assert "409" in str(exc)
