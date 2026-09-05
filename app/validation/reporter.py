from __future__ import annotations

import re

from app.validation.models import TestFailure, TestResult, ValidationReport


class Reporter:
    """Parse test output and extract failure details."""

    def parse(self, result: TestResult, language: str = "python") -> ValidationReport:
        failures = self._extract_failures(result.output, language)
        total = self._count_tests(result.output, language)
        summary = self._summarize(result.output)

        return ValidationReport(
            passed=result.passed,
            total_tests=total,
            failures=failures,
            summary=summary,
            raw_output=result.output[:5000],
        )

    def _extract_failures(self, output: str, language: str) -> list[TestFailure]:
        parsers = {
            "python": self._parse_pytest,
            "javascript": self._parse_jest,
            "typescript": self._parse_jest,
            "go": self._parse_go_test,
            "ruby": self._parse_rspec,
            "java": self._parse_junit,
        }
        parser = parsers.get(language, self._parse_generic)
        return parser(output)

    def _parse_pytest(self, output: str) -> list[TestFailure]:
        failures = []
        pattern = re.compile(r"FAILED\s+(\S+?)::(\S+)\s*[-:]\s*(.*)")
        for match in pattern.finditer(output):
            failures.append(TestFailure(
                test_name=f"{match.group(1)}::{match.group(2)}",
                file=match.group(1).split("::")[0] if "::" in match.group(1) else None,
                message=match.group(3).strip(),
            ))
        return failures

    def _parse_jest(self, output: str) -> list[TestFailure]:
        failures = []
        pattern = re.compile(r"FAIL\s+(.+?)\.test\.(js|ts|jsx|tsx)")
        for match in pattern.finditer(output):
            failures.append(TestFailure(
                test_name=match.group(1),
                file=match.group(0).split(" ")[1] if " " in match.group(0) else None,
            ))

        fail_pattern = re.compile(r"✕\s+(.+)")
        for match in fail_pattern.finditer(output):
            if not any(f.test_name == match.group(1) for f in failures):
                failures.append(TestFailure(test_name=match.group(1).strip()))
        return failures

    def _parse_go_test(self, output: str) -> list[TestFailure]:
        failures = []
        pattern = re.compile(r"--- FAIL:\s+(\S+)\s+\(([^)]+)\)")
        for match in pattern.finditer(output):
            failures.append(TestFailure(
                test_name=match.group(1),
                message=f"Failed after {match.group(2)}",
            ))
        return failures

    def _parse_rspec(self, output: str) -> list[TestFailure]:
        failures = []
        pattern = re.compile(r"rspec\s+(\S+):(\d+)")
        for match in pattern.finditer(output):
            failures.append(TestFailure(
                test_name=f"line {match.group(2)}",
                file=match.group(1),
                line=int(match.group(2)),
            ))
        return failures

    def _parse_junit(self, output: str) -> list[TestFailure]:
        failures = []
        pattern = re.compile(r"Tests run: \d+, Failures: (\d+), Errors: (\d+)")
        for match in pattern.finditer(output):
            if int(match.group(1)) > 0 or int(match.group(2)) > 0:
                failures.append(TestFailure(
                    test_name="JUnit test suite",
                    message=f"Failures: {match.group(1)}, Errors: {match.group(2)}",
                ))
        return failures

    def _parse_generic(self, output: str) -> list[TestFailure]:
        failures = []
        if "error" in output.lower() or "fail" in output.lower():
            lines = output.split("\n")
            for line in lines:
                if "error" in line.lower() or "fail" in line.lower():
                    failures.append(TestFailure(test_name=line.strip()[:200]))
                    if len(failures) >= 10:
                        break
        return failures

    def _count_tests(self, output: str, language: str) -> int:
        patterns = [
            re.compile(r"(\d+) passed"),
            re.compile(r"Ran (\d+) test"),
            re.compile(r"Tests run: (\d+)"),
            re.compile(r"(\d+) test(s)? passed"),
        ]
        for pattern in patterns:
            match = pattern.search(output)
            if match:
                return int(match.group(1))
        return 0

    def _summarize(self, output: str) -> str:
        lines = output.strip().split("\n")
        summary_lines = lines[-5:] if len(lines) > 5 else lines
        return "\n".join(summary_lines)
