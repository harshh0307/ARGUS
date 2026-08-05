"""Full-pipeline live demo: detection -> scan -> fix -> PR -> CI -> self-heal.

Creates (or reuses) harshh0307/argus-demo-repo, seeds it with a repo that calls
removed GitHub API endpoints, then runs the Argus pipeline against it and
watches the CI feedback loop until the PR is green.
"""

from __future__ import annotations

import tempfile
import time
from dataclasses import replace
from pathlib import Path

from app.core.config import get_settings
from app.detection.detect import run_detection
from app.fix.agent import build_suggestion_model
from app.github.client import GitHubClient
from app.github.pr import build_pr_body, run_pr_loop
from app.scan.impact import assess_impact
from app.scan.scanner import ApiScanner

OWNER = "harshh0307"
REPO = "argus-demo-repo"

ORIGINAL_APP = """\
import requests

BASE = "https://api.github.com"

def protect_tags(owner, repo):
    resp = requests.get(f"{BASE}/repos/{owner}/{repo}/tags/protection")
    return resp.json()

def dependabot_access(org):
    resp = requests.get(f"{BASE}/organizations/{org}/dependabot/repository-access")
    return resp.json()

def get_repo(owner, repo):
    resp = requests.get(f"{BASE}/repos/{owner}/{repo}")
    return resp.json()
"""

CI_YML = """\
name: ci
on:
  push:
  pull_request:

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Exercise GitHub API usage
        run: |
          pip install requests
          python - <<'PY'
          from app import protect_tags, dependabot_access, get_repo

          protect_tags("harshh0307", "argus-demo-repo")
          dependabot_access("harshh0307")
          get_repo("harshh0307", "argus-demo-repo")
          print("API usage OK")
          PY
"""


def seed_repo(client: GitHubClient) -> str:
    if not client.repo_exists(OWNER, REPO):
        print(f"[demo] creating {OWNER}/{REPO}")
        client.create_repo(REPO, private=False, description="Argus self-heal demo target")
        info = None
        for _ in range(15):
            info = client.get_repo_info(OWNER, REPO)
            if info is not None:
                break
            time.sleep(2)
        if info is None:
            raise RuntimeError("repo did not appear after creation")
    else:
        info = client.get_repo_info(OWNER, REPO)
    default_branch = info["default_branch"]
    files = {
        "README.md": f"# {REPO}\n\nDemo target repo for the Argus self-heal pipeline.\n",
        ".github/workflows/ci.yml": CI_YML,
        "app.py": ORIGINAL_APP,
    }
    for path, content in files.items():
        if client.get_file(OWNER, REPO, path, ref=default_branch) is None:
            print(f"[demo] seeding {path}")
            client.create_file(OWNER, REPO, path, f"seed {path}", content, default_branch)
    return default_branch


def reset_pr_state(client: GitHubClient, branch: str) -> None:
    existing = client.find_open_pull(OWNER, REPO, branch)
    if existing is not None:
        print(f"[demo] closing stale PR #{existing}")
        client.close_pull(OWNER, REPO, existing)
    if client.get_ref(OWNER, REPO, branch) is not None:
        print(f"[demo] deleting stale branch {branch}")
        client.delete_branch(OWNER, REPO, branch)


def main() -> None:
    settings = get_settings()
    client = GitHubClient(token=settings.github_token)

    base = seed_repo(client)
    reset_pr_state(client, "argus/fix")

    detection = run_detection(settings)
    print(f"[demo] detection: {detection['breaking_count']} breaking, "
          f"{detection['additive_count']} additive changes")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "app.py").write_text(ORIGINAL_APP, encoding="utf-8")
        usages = ApiScanner(base_url="https://api.github.com").scan(tmp_path)
        impacts = assess_impact(usages, detection["changes"])

    impacts = [replace(i, usage=replace(i.usage, file="app.py")) for i in impacts]
    print(f"[demo] {len(impacts)} impacted call sites in app.py")
    for impact in impacts:
        print(f"  - {impact}")

    if not impacts:
        print("[demo] nothing to fix; exiting")
        return

    body = build_pr_body(
        f"Argus found {len(impacts)} breaking API change(s) in this repo.",
        [f"{i.change.method.upper()} {i.change.path}: {i.change.detail}" for i in impacts],
    )
    result = run_pr_loop(
        client,
        OWNER,
        REPO,
        base=base,
        branch="argus/fix",
        files={"app.py": ORIGINAL_APP},
        impacts=impacts,
        suggestion_model=build_suggestion_model(settings),
        max_attempts=3,
        check_timeout=600,
        check_interval=15,
        title="argus: fix breaking GitHub API changes",
        body=body,
    )
    print(f"[demo] PR #{result.pr_number}: {result.pr_url}")
    print(f"[demo] passed={result.passed} attempts={result.attempts}")
    if result.failure:
        print(f"[demo] last failure: {result.failure[:500]}")


if __name__ == "__main__":
    main()
