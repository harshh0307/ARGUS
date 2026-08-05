from __future__ import annotations

from pydantic import BaseModel


class CheckResult(BaseModel):
    name: str
    status: str
    conclusion: str | None = None


class PullRequest(BaseModel):
    number: int
    head_sha: str
    html_url: str
