from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from app.core.config import Settings
from app.git.base import GitCheck, GitPR, GitProvider, GitRepo


class GitHubProvider(GitProvider):
    """GitHub REST API provider with git-clone fallback for checkout."""

    def __init__(self, settings: Settings):
        super().__init__(settings)
        self._token = settings.github_token
        self._base_url = "https://api.github.com"
        self._client = httpx.Client(
            timeout=30,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        resp = self._client.request(method, f"{self._base_url}{path}", **kwargs)
        if resp.status_code >= 400:
            from app.git.base import _GitApiError
            raise _GitApiError(f"GitHub API {resp.status_code}: {resp.text[:200]}")
        return resp

    def get_repo(self, owner: str, name: str) -> GitRepo | None:
        try:
            resp = self._request("GET", f"/repos/{owner}/{name}")
            data = resp.json()
            return GitRepo(
                owner=owner,
                name=name,
                default_branch=data.get("default_branch", "main"),
                private=data.get("private", False),
                provider="github",
            )
        except Exception:  # noqa: BLE001
            return None

    def checkout(self, owner: str, name: str, ref: str, dest: Path) -> None:
        try:
            resp = self._request("GET", f"/repos/{owner}/{name}/tarball/{ref}")
            self._extract_tarball(resp.content, dest)
        except Exception:  # noqa: BLE001
            url = f"https://x-access-token:{self._token}@github.com/{owner}/{name}.git"
            self._git_clone(url, ref, dest)

    def create_branch(self, owner: str, name: str, branch: str, base: str) -> None:
        ref_resp = self._request("GET", f"/repos/{owner}/{name}/git/ref/heads/{base}")
        sha = ref_resp.json()["object"]["sha"]
        self._request(
            "POST",
            f"/repos/{owner}/{name}/git/refs",
            json={"ref": f"refs/heads/{branch}", "sha": sha},
        )

    def push_files(self, owner: str, name: str, branch: str, files: dict[str, str]) -> None:
        import base64

        for filepath, content in files.items():
            resp = self._request(
                "GET",
                f"/repos/{owner}/{name}/contents/{filepath}",
                params={"ref": branch},
            )
            if resp.status_code == 200:
                sha = resp.json().get("sha")
                self._request(
                    "PUT",
                    f"/repos/{owner}/{name}/contents/{filepath}",
                    json={
                        "message": f"Argus: update {filepath}",
                        "content": base64.b64encode(content.encode()).decode(),
                        "sha": sha,
                        "branch": branch,
                    },
                )
            else:
                self._request(
                    "PUT",
                    f"/repos/{owner}/{name}/contents/{filepath}",
                    json={
                        "message": f"Argus: add {filepath}",
                        "content": base64.b64encode(content.encode()).decode(),
                        "branch": branch,
                    },
                )

    def open_pr(
        self, owner: str, name: str, branch: str, base: str, title: str, body: str
    ) -> GitPR:
        resp = self._request(
            "POST",
            f"/repos/{owner}/{name}/pulls",
            json={"title": title, "body": body, "head": branch, "base": base},
        )
        data = resp.json()
        return GitPR(
            number=data["number"],
            url=data["html_url"],
            title=data.get("title", ""),
            state=data.get("state", "open"),
        )

    def get_checks(self, owner: str, name: str, ref: str) -> list[GitCheck]:
        try:
            resp = self._request("GET", f"/repos/{owner}/{name}/commits/{ref}/check-runs")
            data = resp.json()
            return [
                GitCheck(
                    name=check["name"],
                    status=check["status"],
                    conclusion=check.get("conclusion"),
                )
                for check in data.get("check_runs", [])
            ]
        except Exception:  # noqa: BLE001
            return []

    def merge_pr(self, owner: str, name: str, pr_number: int) -> None:
        self._request(
            "PUT",
            f"/repos/{owner}/{name}/pulls/{pr_number}/merge",
            json={"merge_method": "squash"},
        )

    def find_open_pr(self, owner: str, name: str, branch: str) -> int | None:
        resp = self._request(
            "GET",
            f"/repos/{owner}/{name}/pulls",
            params={"head": f"{owner}:{branch}", "state": "open"},
        )
        prs = resp.json()
        if prs:
            return prs[0]["number"]
        return None

    def close_pr(self, owner: str, name: str, pr_number: int) -> None:
        self._request(
            "PATCH",
            f"/repos/{owner}/{name}/pulls/{pr_number}",
            json={"state": "closed"},
        )

    def list_repos(self) -> list[GitRepo]:
        if self._token:
            resp = self._request("GET", "/user/repos", params={"per_page": "100"})
        else:
            return []
        return [
            GitRepo(
                owner=r["owner"]["login"],
                name=r["name"],
                default_branch=r.get("default_branch", "main"),
                private=r.get("private", False),
                provider="github",
            )
            for r in resp.json()
        ]
