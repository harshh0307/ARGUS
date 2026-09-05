from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TestResult:
    passed: bool
    exit_code: int
    output: str
    duration_seconds: float = 0.0


@dataclass
class TestFailure:
    test_name: str
    file: str | None = None
    line: int | None = None
    message: str = ""


@dataclass
class ValidationReport:
    passed: bool
    total_tests: int = 0
    failures: list[TestFailure] = field(default_factory=list)
    summary: str = ""
    raw_output: str = ""
