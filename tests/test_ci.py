import pytest

from app.github.ci import CiTimeoutError, failure_message, wait_for_checks
from app.github.models import CheckResult


def check(name, status, conclusion=None):
    return CheckResult(name=name, status=status, conclusion=conclusion)


class FakeCiClient:
    def __init__(self, sequence, log=None):
        self.sequence = list(sequence)
        self.log = log
        self.calls = 0

    def check_runs(self, owner, repo, ref):
        self.calls += 1
        if len(self.sequence) == 1:
            return self.sequence[0]
        return self.sequence.pop(0)

    def failure_log(self, owner, repo, ref, check_name):
        return self.log


def test_wait_for_checks_returns_completed():
    client = FakeCiClient(
        [
            [check("ci", "in_progress")],
            [check("ci", "completed", "success")],
        ]
    )
    result = wait_for_checks(client, "o", "r", "head-1", timeout=5, interval=0.01)
    assert result == [check("ci", "completed", "success")]
    assert client.calls == 2


def test_wait_for_checks_times_out():
    client = FakeCiClient([[check("ci", "in_progress")]])
    with pytest.raises(CiTimeoutError):
        wait_for_checks(client, "o", "r", "head-1", timeout=0.05, interval=0.01)


def test_failure_message_none_when_passing():
    client = FakeCiClient([], log="unused")
    checks = [check("ci", "completed", "success")]
    assert failure_message(client, "o", "r", "head-1", checks) is None


def test_failure_message_tails_failed_log():
    client = FakeCiClient([])
    log = "x" * 3000
    client.log = log
    checks = [check("ci", "completed", "failure"), check("lint", "completed", "failure")]
    msg = failure_message(client, "o", "r", "head-1", checks)
    assert "### ci" in msg
    assert "### lint" in msg
    assert msg[-1500:] == "x" * 1500


def test_failure_message_reports_missing_log():
    client = FakeCiClient([])
    checks = [check("ci", "completed", "failure")]
    msg = failure_message(client, "o", "r", "head-1", checks)
    assert "no log available" in msg


def test_failure_message_windows_around_error_marker():
    client = FakeCiClient([])
    log = (
        "pre\n" * 40
        + "2026-08-05T08:00:00Z Traceback (most recent call last):\n"
        + "2026-08-05T08:00:00Z ImportError: cannot import name 'x'\n"
        + "2026-08-05T08:00:00Z ##[error]Process completed with exit code 1.\n"
        + "cleanup noise\n" * 40
    )
    client.log = log
    checks = [check("ci", "completed", "failure")]
    msg = failure_message(client, "o", "r", "head-1", checks)
    assert "ImportError" in msg
    assert "##[error]" in msg
    assert "cleanup noise" not in msg