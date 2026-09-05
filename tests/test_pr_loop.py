from app.fix.models import PatchSuggestion
from app.scan.models import DriftSignal
from app.github.models import CheckResult, PullRequest
from app.github.pr import build_pr_body, run_pr_loop
from app.scan.models import Impact, Usage


def check(name, conclusion):
    return CheckResult(name=name, status="completed", conclusion=conclusion)


def impact(file, line, path="/repos/{owner}/{repo}/tags/protection"):
    return Impact(
        usage=Usage(file=str(file), line=line, method="get", path=path),
        change=DriftSignal(kind="endpoint_removed", severity="breaking", path=path, method="get", detail="endpoint is no longer documented"),
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
        ),
        PatchSuggestion(
            file="app.py",
            line=2,
            action="replace",
            replacement='resp = requests.get("https://api.github.com/repos/me/x/collaborators")',
        ),
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
    assert "collaborators" in fake.files["app.py"]["content"]
    assert "collaborators" in fake.pushes[1][1]
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
        ),
        PatchSuggestion(
            file="app.py",
            line=2,
            action="replace",
            replacement='resp = requests.get("https://api.github.com/repos/me/x/collaborators")',
        ),
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


class FailingSuggestionModel:
    def suggest(self, prompt):
        return PatchSuggestion(file="app.py", line=2, action="replace", replacement="")  # invalid


def test_all_fixes_failed_aborts_without_pr():
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
        suggestion_model=FailingSuggestionModel(),
        check_interval=0.01,
    )
    assert not result.passed
    assert result.attempts == 0
    assert result.pr_number == 0
    assert "failed to produce any patch" in result.failure
    assert fake.pushes == []
    assert fake.comments == []


def test_partial_fix_failure_comments_on_pr():
    fake = FakeGitHub(check_script=[[check("ci", "success")]])
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
        impacts=[impact("app.py", 2), impact("app.py", 9)],
        suggestion_model=model,
        check_interval=0.01,
    )
    assert result.passed
    assert any("initial fix failed on 1 call site" in c for c in fake.comments)


class EchoSuggestionModel:
    def suggest(self, prompt):
        return PatchSuggestion(file="app.py", line=2, action="replace", replacement='resp = requests.get("x")')


def test_retry_with_no_new_patches_gives_up_without_repush():
    fake = FakeGitHub(check_script=[[check("ci", "failure")]], log="NameError: broken")
    files = {"app.py": "import requests\nresp = requests.get('x')\n"}
    result = run_pr_loop(
        fake,
        "o",
        "r",
        base="main",
        branch="argus/fix",
        files=files,
        impacts=[impact("app.py", 2)],
        suggestion_model=EchoSuggestionModel(),
        max_attempts=3,
        check_interval=0.01,
    )
    assert not result.passed
    assert result.attempts == 1
    assert "no new patches" in result.failure
    assert any("giving up" in c for c in fake.comments)
    assert len(fake.pushes) == 1  # only the initial push; no identical re-push
