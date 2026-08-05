from __future__ import annotations

import base64

import httpx

from app.github.models import CheckResult, PullRequest


class GitHubApiError(Exception):
    pass


class GitHubClient:
    def __init__(
        self,
        token: str,
        base_url: str = "https://api.github.com",
        timeout: float = 30.0,
        client: httpx.Client | None = None,
    ):
        if not token:
            raise ValueError("a GitHub token is required to build a GitHubClient")
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "argus/0.1 (api-change-agent)",
            },
            timeout=timeout,
        )

    def _request(self, method: str, path: str, **kwargs) -> dict | None:
        response = self._client.request(method, f"{self._base_url}{path}", **kwargs)
        if response.status_code == 404:
            return None
        if response.status_code == 204:
            return {}
        if response.status_code >= 400:
            raise GitHubApiError(
                f"{method} {path} -> {response.status_code}: {response.text[:300]}"
            )
        return response.json()

    def _request_text(self, method: str, path: str, **kwargs) -> str | None:
        response = self._client.request(method, f"{self._base_url}{path}", **kwargs)
        if response.status_code == 404:
            return None
        if response.status_code >= 400:
            raise GitHubApiError(
                f"{method} {path} -> {response.status_code}: {response.text[:300]}"
            )
        return response.text

    def branch_head_sha(self, owner: str, repo: str, branch: str) -> str:
        data = self._request("GET", f"/repos/{owner}/{repo}/branches/{branch}")
        if data is None:
            raise GitHubApiError(f"branch {owner}/{repo}:{branch} not found")
        return data["commit"]["sha"]

    def get_ref(self, owner: str, repo: str, branch: str) -> str | None:
        data = self._request("GET", f"/repos/{owner}/{repo}/git/ref/heads/{branch}")
        if data is None:
            return None
        return data["object"]["sha"]

    def create_branch(self, owner: str, repo: str, branch: str, sha: str) -> None:
        self._request(
            "POST",
            f"/repos/{owner}/{repo}/git/refs",
            json={"ref": f"refs/heads/{branch}", "sha": sha},
        )

    def get_file(self, owner: str, repo: str, path: str, ref: str | None = None) -> dict | None:
        params = {}
        if ref:
            params["ref"] = ref
        data = self._request("GET", f"/repos/{owner}/{repo}/contents/{path}", params=params)
        if data is None:
            return None
        return {
            "content": base64.b64decode(data["content"]).decode("utf-8"),
            "sha": data["sha"],
        }

    def create_file(
        self, owner: str, repo: str, path: str, message: str, content: str, branch: str
    ) -> None:
        self._request(
            "PUT",
            f"/repos/{owner}/{repo}/contents/{path}",
            json={
                "message": message,
                "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"),
                "branch": branch,
            },
        )

    def update_file(
        self,
        owner: str,
        repo: str,
        path: str,
        message: str,
        content: str,
        sha: str,
        branch: str,
    ) -> None:
        self._request(
            "PUT",
            f"/repos/{owner}/{repo}/contents/{path}",
            json={
                "message": message,
                "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"),
                "sha": sha,
                "branch": branch,
            },
        )

    def open_pull_request(
        self, owner: str, repo: str, title: str, head: str, base: str, body: str
    ) -> PullRequest:
        data = self._request(
            "POST",
            f"/repos/{owner}/{repo}/pulls",
            json={"title": title, "head": head, "base": base, "body": body},
        )
        return PullRequest(number=data["number"], head_sha=data["head"]["sha"], html_url=data["html_url"])

    def get_pull(self, owner: str, repo: str, number: int) -> PullRequest:
        data = self._request("GET", f"/repos/{owner}/{repo}/pulls/{number}")
        return PullRequest(number=data["number"], head_sha=data["head"]["sha"], html_url=data["html_url"])

    def check_runs(self, owner: str, repo: str, ref: str) -> list[CheckResult]:
        data = self._request("GET", f"/repos/{owner}/{repo}/commits/{ref}/check-runs")
        if data is None:
            return []
        return [
            CheckResult(name=item["name"], status=item["status"], conclusion=item.get("conclusion"))
            for item in data.get("check_runs", [])
        ]

    def failure_log(self, owner: str, repo: str, ref: str, check_name: str) -> str | None:
        runs = self._request(
            "GET",
            f"/repos/{owner}/{repo}/actions/runs",
            params={"head_sha": ref, "status": "failure", "per_page": 1},
        )
        if not runs or not runs.get("workflow_runs"):
            return None
        run_id = runs["workflow_runs"][0]["id"]
        jobs = self._request("GET", f"/repos/{owner}/{repo}/actions/runs/{run_id}/jobs")
        if not jobs or not jobs.get("jobs"):
            return None
        job_id = None
        for job in jobs["jobs"]:
            if job["name"] == check_name:
                job_id = job["id"]
                break
        if job_id is None:
            job_id = jobs["jobs"][0]["id"]
        return self._request_text("GET", f"/repos/{owner}/{repo}/actions/jobs/{job_id}/logs")

    def pr_comment(self, owner: str, repo: str, number: int, body: str) -> None:
        self._request(
            "POST",
            f"/repos/{owner}/{repo}/issues/{number}/comments",
            json={"body": body},
        )
