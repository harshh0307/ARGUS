from __future__ import annotations

import time

from app.github.models import CheckResult


class CiTimeoutError(Exception):
    pass


def wait_for_checks(
    client,
    owner: str,
    repo: str,
    ref: str,
    timeout: float = 300.0,
    interval: float = 10.0,
) -> list[CheckResult]:
    deadline = time.monotonic() + timeout
    while True:
        checks = client.check_runs(owner, repo, ref)
        if checks and all(check.status == "completed" for check in checks):
            return checks
        if time.monotonic() >= deadline:
            raise CiTimeoutError(f"checks for {owner}/{repo}@{ref} did not complete within {timeout}s")
        time.sleep(interval)


def failure_message(
    client,
    owner: str,
    repo: str,
    ref: str,
    checks: list[CheckResult],
    max_chars: int = 1500,
) -> str | None:
    failed = [check for check in checks if check.conclusion == "failure"]
    if not failed:
        return None
    chunks = []
    for check in failed:
        log = client.failure_log(owner, repo, ref, check.name)
        if log:
            chunks.append(f"### {check.name}\n{log[-max_chars:]}")
        else:
            chunks.append(f"### {check.name}\n(no log available)")
    return "\n\n".join(chunks)
