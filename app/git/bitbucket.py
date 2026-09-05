from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from app.core.config import Settings
from app.git.base import GitCheck, GitPR, GitProvider, GitRepo


class BitbucketProvider(GitProvider):
    """Bitbucket API provider with git-clone fallback."""

    def __init__(self, settings: Settings):
        super().__init__(settings)
        self._token = settings.bitbucket_token
        self._workspace = settings.bitbucket_workspace
        self._base_url = "https://api.bitbucket.org/2.0"
        self._client = httpx.Client(
            timeout=30,
            auth=("x-token-auth", self._token) if self._token else None,
        )

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        resp = self._client.request(method, f"{self._base_url}{path}", **kwargs)
        if resp.status_code >= 400:
            raise RuntimeError(f"Bitbucket API {resp.status_code}: {resp.text[:200]}")
        return resp

    def _repo_path(self, owner: str, name: str) -> str:
        return f"/repositories/{owner}/{name}"

    def get_repo(self, owner: str, name: str) -> GitRepo | None:
        try:
            resp = self._request("GET", self._repo_path(owner, name))
            data = resp.json()
            return GitRepo(
                owner=owner,
                name=name,
                default_branch=data.get("mainbranch", {}).get("name", "main"),
                private=data.get("is_private", True),
                provider="bitbucket",
            )
        except Exception:  # noqa: BLE001
            return None

    def checkout(self, owner: str, name: str, ref: str, dest: Path) -> None:
        try:
            resp = self._request(
                "GET",
                f"{self._repo_path(owner, name)}/download/{ref}.tar.gz",
            )
            self._extract_tarball(resp.content, dest)
        except Exception:  # noqa: BLE001
            url = f"https://x-token-auth:{self._token}@bitbucket.org/{owner}/{name}.git"
            self._git_clone(url, ref, dest)

    def create_branch(self, owner: str, name: str, branch: str, base: str) -> None:
        self._request(
            "POST",
            f"{self._repo_path(owner, name)}/refs/branches",
            json={"name": branch, "target": {"hash": base}},
        )

    def push_files(self, owner: str, name: str, branch: str, files: dict[str, str]) -> None:
        import base64
        for filepath, content in files.items():
            encoded = base64.b64encode(content.encode()).decode()
            self._request(
                "POST",
                f"{self._repo_path(owner, name)}/src/{branch}/{filepath}",
                json={"content": encoded, "message": f"Argus: update {filepath}"},
            )

    def open_pr(
        self, owner: str, name: str, branch: str, base: str, title: str, body: str
    ) -> GitPR:
        resp = self._request(
            "POST",
            f"{self._repo_path(owner, name)}/pullrequests",
            json={
                "title": title,
                "description": body,
                "source": {"branch": {"name": branch}},
                "destination": {"branch": {"name": base}},
            },
        )
        data = resp.json()
        return GitPR(
            number=data["id"],
            url=data["links"]["html"]["href"],
            title=data.get("title", ""),
            state=data.get("state", "OPEN"),
        )

    def get_checks(self, owner: str, name: str, ref: str) -> list[GitCheck]:
        return []

    def merge_pr(self, owner: str, name: str, pr_number: int) -> None:
        self._request(
            "POST",
            f"{self._repo_path(owner, name)}/pullrequests/{pr_number}/merge",
        )

    def find_open_pr(self, owner: str, name: str, branch: str) -> int | None:
        resp = self._request(
            "GET",
            f"{self._repo_path(owner, name)}/pullrequests",
            params={"q": f'source.branch.name="{branch}" AND state="OPEN"'},
        )
        prs = resp.json().get("values", [])
        if prs:
            return prs[0]["id"]
        return None

    def close_pr(self, owner: str, name: str, pr_number: int) -> None:
        self._request(
            "PUT",
            f"{self._repo_path(owner, name)}/pullrequests/{pr_number}",
            json={"state": "SUPERSEDED"},
        )

    def list_repos(self) -> list[GitRepo]:
        resp = self._request("GET", "/repositories", params={"role": "member"})
        return [
            GitRepo(
                owner=r["workspace"]["slug"],
                name=r["slug"],
                default_branch=r.get("mainbranch", {}).get("name", "main"),
                private=r.get("is_private", True),
                provider="bitbucket",
            )
            for r in resp.json().get("values", [])
        ]
