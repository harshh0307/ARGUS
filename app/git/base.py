from __future__ import annotations

import io
import subprocess
import tarfile
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass
class GitRepo:
    owner: str
    name: str
    default_branch: str = "main"
    private: bool = False
    provider: str = ""


@dataclass
class GitPR:
    number: int
    url: str
    title: str = ""
    state: str = "open"


@dataclass
class GitCheck:
    name: str
    status: str  # "completed" | "pending" | "in_progress"
    conclusion: str | None = None  # "success" | "failure" | None
    output: str = ""


class GitProvider(ABC):
    """Abstract interface for Git hosting providers."""

    def __init__(self, settings):
        self.settings = settings

    @abstractmethod
    def get_repo(self, owner: str, name: str) -> GitRepo | None:
        ...

    @abstractmethod
    def checkout(self, owner: str, name: str, ref: str, dest: Path) -> None:
        """Download repo contents to dest directory."""
        ...

    @abstractmethod
    def create_branch(self, owner: str, name: str, branch: str, base: str) -> None:
        ...

    @abstractmethod
    def push_files(self, owner: str, name: str, branch: str, files: dict[str, str]) -> None:
        """Push files to a branch. keys are file paths, values are contents."""
        ...

    @abstractmethod
    def open_pr(
        self, owner: str, name: str, branch: str, base: str, title: str, body: str
    ) -> GitPR:
        ...

    @abstractmethod
    def get_checks(self, owner: str, name: str, ref: str) -> list[GitCheck]:
        ...

    @abstractmethod
    def merge_pr(self, owner: str, name: str, pr_number: int) -> None:
        ...

    @abstractmethod
    def find_open_pr(self, owner: str, name: str, branch: str) -> int | None:
        ...

    @abstractmethod
    def close_pr(self, owner: str, name: str, pr_number: int) -> None:
        ...

    @abstractmethod
    def list_repos(self) -> list[GitRepo]:
        ...

    def _git_clone(self, url: str, ref: str, dest: Path) -> None:
        subprocess.run(
            ["git", "clone", "--depth=1", f"--branch={ref}", url, str(dest)],
            check=True,
            capture_output=True,
            timeout=120,
        )

    def _extract_tarball(self, data: bytes, dest: Path) -> None:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            for member in tar.getmembers():
                parts = Path(member.name).parts[1:]
                if not parts:
                    continue
                member.name = str(Path(*parts))
            try:
                tar.extractall(dest, filter="data")
            except TypeError:
                tar.extractall(dest)
