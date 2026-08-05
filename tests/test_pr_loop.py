from app.detection.models import BREAKING, Change
from app.fix.models import PatchSuggestion
from app.github.models import CheckResult, PullRequest
from app.github.pr import build_pr_body, run_pr_loop
from app.scan.models import Impact, Usage


def check(name, conclusion):
    return CheckResult(name=name, status="completed", conclusion=conclusion)


def impact(file, line, path="/repos/{owner}/{repo}/tags/protection"):
    return Impact(
        usage=Usage(file=str(file), line=line, method="get", path=path),
        change=Change("endpoint_removed", BREAKING, path, "get", "endpoint is no longer documented"),
    )


class FakeSuggestionModel:
    def __init__(self, *suggestions):
        self.suggestions = list(suggestions)
        self.calls = 0

    def suggest(self, prompt):
        self.calls += 1
        if self.suggestions:
            return self.suggestions.pop(0)
        return PatchSuggestion(file="", line=1)


class FakeGitHub:
    def __init__(self, check_script, log="ci failure log"):
        self.check_script = list(check_script)
        self.log = log
        self.comments = []
        self.pushes = []
        self.files = {}
        self.branch_created = False
        self.head = "head-1"
        self.pr = PullRequest(number=1, head_sha="head-1", html_url="https://github.com/o/r/pull/1")

    def branch_head_sha(self, owner, repo, branch):
        return "base-sha" if branch == "main" else self.head

    def get_ref(self, owner, repo, branch):
        return None if not self.branch_created else "base-sha"

    def create_branch(self, owner, repo, branch, sha):
        self.branch_created = True

    def get_file(self, owner, repo, path, ref=None):
        return self.files.get(path)

    def create_file(self, owner, repo, path, message, content, branch):
        self.files[path] = {"content": content, "sha": f"sha-{len(self.files)}"}
        self.pushes.append((path, content, message))
        self.head = f"head-{len(self.pushes) + 1}"

    def update_file(self, owner, repo, path, message, content, sha, branch):
        self.files[path] = {"content": content, "sha": f"sha-{len(self.files)}"}
        self.pushes.append((path, content, message))
        self.head = f"head-{len(self.pushes) + 1}"

    def open_pull_request(self, owner, repo, title, head, base, body):
        return self.pr

    def check_runs(self, owner, repo, ref):
        if len(self.check_script) == 1:
            return self.check_script[0]
        return self.check_script.pop(0)

    def failure_log(self, owner, repo, ref, check_name):
        return self.log

    def pr_comment(self, owner, repo, number, body):
        self.comments.append(body)


def test_happy_path_opens_pr_and_passes():
    fake = FakeGitHub(check_script=[[check("ci", "success")]])
    files = {"app.py": "import requests\nresp = requests.get('x')\n"}
    result = run_pr_loop(
        fake,
        "o",
        "r",
        base="main",
        branch="argus/fix",
        files=files,
        impacts=[impact("app.py", 2)],
        suggestion_model=FakeSuggestionModel(),
        check_interval=0.01,
    )
    assert result.passed
    assert result.attempts == 1
    assert result.pr_number == 1
    assert fake.branch_created
    assert len(fake.pushes) == 1
    assert fake.comments == []


def test_ci_fail_then_fix_loop():
    fake = FakeGitHub(
        check_script=[[check("ci", "failure")], [check("ci", "success")]],
        log="NameError: resp is not defined",
    )
    files = {"app.py": "import requests\nresp = requests.get('x')\n"}
    model = FakeSuggestionModel(
        PatchSuggestion(
            file="app.py",
            line=2,
            action="replace",
            replacement='resp = requests.get("https://api.github.com/repos/me/x/branches")',
        )
    )
    result = run_pr_loop(
        fake,
        "o",
        "r",
        base="main",
        branch="argus/fix",
        files=files,
        impacts=[impact("app.py", 2)],
        suggestion_model=model,
        check_interval=0.01,
    )
    assert result.passed
    assert result.attempts == 2
    assert "branches" in fake.files["app.py"]["content"]
    assert "branches" in fake.pushes[0][1]
    assert len(fake.pushes) == 2
    assert any("CI failed on attempt 1" in c for c in fake.comments)
    assert "NameError" in fake.comments[0]


def test_gives_up_after_max_attempts():
    fake = FakeGitHub(
        check_script=[[check("ci", "failure")], [check("ci", "failure")]],
        log="still broken",
    )
    files = {"app.py": "import requests\nresp = requests.get('x')\n"}
    model = FakeSuggestionModel(
        PatchSuggestion(
            file="app.py",
            line=2,
            action="replace",
            replacement='resp = requests.get("https://api.github.com/repos/me/x/branches")',
        )
    )
    result = run_pr_loop(
        fake,
        "o",
        "r",
        base="main",
        branch="argus/fix",
        files=files,
        impacts=[impact("app.py", 2)],
        suggestion_model=model,
        max_attempts=2,
        check_interval=0.01,
    )
    assert not result.passed
    assert result.attempts == 2
    assert any("giving up after 2 attempt" in c for c in fake.comments)


def test_build_pr_body():
    body = build_pr_body("Argus fixed 2 breaking changes.", ["GET /x removed", "POST /y changed"])
    assert "Argus fixed 2 breaking changes." in body
    assert "- GET /x removed" in body
    assert "- POST /y changed" in body
