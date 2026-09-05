from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import httpx

from app.core.config import Settings
from app.git.base import GitCheck, GitPR, GitProvider, GitRepo


class GitLabProvider(GitProvider):
    """GitLab API provider with git-clone fallback."""

    def __init__(self, settings: Settings):
        super().__init__(settings)
        self._token = settings.gitlab_token
        self._base_url = settings.gitlab_url.rstrip("/")
        self._client = httpx.Client(
            timeout=30,
            headers={"PRIVATE-TOKEN": self._token} if self._token else {},
        )

    def _project_path(self, owner: str, name: str) -> str:
        return f"{owner}%2F{name}"

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        resp = self._client.request(method, f"{self._base_url}/api/v4{path}", **kwargs)
        if resp.status_code >= 400:
            raise RuntimeError(f"GitLab API {resp.status_code}: {resp.text[:200]}")
        return resp

    def get_repo(self, owner: str, name: str) -> GitRepo | None:
        try:
            resp = self._request("GET", f"/projects/{self._project_path(owner, name)}")
            data = resp.json()
            return GitRepo(
                owner=owner,
                name=name,
                default_branch=data.get("default_branch", "main"),
                private=data.get("visibility", "private") == "private",
                provider="gitlab",
            )
        except Exception:
            return None

    def checkout(self, owner: str, name: str, ref: str, dest: Path) -> None:
        try:
            resp = self._request(
                "GET",
                f"/projects/{self._project_path(owner, name)}/repository/archive.tar.gz",
                params={"sha": ref},
            )
            self._extract_tarball(resp.content, dest)
        except Exception:
            url = f"https://oauth2:{self._token}@gitlab.com/{owner}/{name}.git"
            self._git_clone(url, ref, dest)

    def create_branch(self, owner: str, name: str, branch: str, base: str) -> None:
        import requests
        resp = self._request(
            "POST",
            f"/projects/{self._project_path(owner, name)}/repository/branches",
            json={"branch": branch, "ref": base},
        )

    def push_files(self, owner: str, name: str, branch: str, files: dict[str, str]) -> None:
        project = self._project_path(owner, name)
        for filepath, content in files.items():
            import base64
            encoded = base64.b64encode(content.encode()).decode()
            self._request(
                "POST",
                f"/projects/{project}/repository/files/{filepath}",
                json={
                    "branch": branch,
                    "content": content,
                    "commit_message": f"Argus: update {filepath}",
                },
            )

    def open_pr(
        self, owner: str, name: str, branch: str, base: str, title: str, body: str
    ) -> GitPR:
        resp = self._request(
            "POST",
            f"/projects/{self._project_path(owner, name)}/merge_requests",
            json={
                "source_branch": branch,
                "target_branch": base,
                "title": title,
                "description": body,
            },
        )
        data = resp.json()
        return GitPR(
            number=data["iid"],
            url=data["web_url"],
            title=data.get("title", ""),
            state=data.get("state", "opened"),
        )

    def get_checks(self, owner: str, name: str, ref: str) -> list[GitCheck]:
        return []

    def merge_pr(self, owner: str, name: str, pr_number: int) -> None:
        self._request(
            "PUT",
            f"/projects/{self._project_path(owner, name)}/merge_requests/{pr_number}/merge",
        )

    def find_open_pr(self, owner: str, name: str, branch: str) -> int | None:
        resp = self._request(
            "GET",
            f"/projects/{self._project_path(owner, name)}/merge_requests",
            params={"source_branch": branch, "state": "opened"},
        )
        mrs = resp.json()
        if mrs:
            return mrs[0]["iid"]
        return None

    def close_pr(self, owner: str, name: str, pr_number: int) -> None:
        self._request(
            "PUT",
            f"/projects/{self._project_path(owner, name)}/merge_requests/{pr_number}",
            json={"state_event": "close"},
        )

    def list_repos(self) -> list[GitRepo]:
        resp = self._request("GET", "/projects", params={"membership": "true", "per_page": "100"})
        return [
            GitRepo(
                owner=r["namespace"]["full_path"],
                name=r["path"],
                default_branch=r.get("default_branch", "main"),
                private=r.get("visibility", "private") == "private",
                provider="gitlab",
            )
            for r in resp.json()
        ]
