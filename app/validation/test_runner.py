from __future__ import annotations

import json
import logging
from pathlib import Path

from app.validation.models import TestResult

logger = logging.getLogger(__name__)


class TestRunner:
    """Detects and runs test frameworks for various languages."""

    def detect_test_command(self, repo_path: Path, language: str) -> str | None:
        detectors = {
            "python": self._detect_python,
            "javascript": self._detect_javascript,
            "typescript": self._detect_typescript,
            "go": self._detect_go,
            "ruby": self._detect_ruby,
            "java": self._detect_java,
        }
        detector = detectors.get(language)
        return detector(repo_path) if detector else None

    def run(
        self,
        repo_path: Path,
        test_command: str | None = None,
        language: str = "python",
    ) -> TestResult:
        from app.core.config import get_settings
        from app.validation.sandbox import Sandbox

        settings = get_settings()
        sandbox = Sandbox(settings)

        if test_command is None:
            test_command = self.detect_test_command(repo_path, language)
        if test_command is None:
            return TestResult(
                passed=True,
                exit_code=0,
                output="No test command detected, skipping tests",
            )

        return sandbox.run_tests(repo_path, test_command, language)

    def _detect_python(self, path: Path) -> str | None:
        if (path / "pytest.ini").exists():
            return "python -m pytest --tb=short -q"
        if (path / "setup.cfg").exists():
            cfg = (path / "setup.cfg").read_text()
            if "[tool:pytest]" in cfg:
                return "python -m pytest --tb=short -q"
        if (path / "pyproject.toml").exists():
            return "python -m pytest --tb=short -q"
        if (path / "Makefile").exists():
            makefile = (path / "Makefile").read_text()
            if "test" in makefile:
                return "make test"
        return "python -m pytest --tb=short -q"

    def _detect_javascript(self, path: Path) -> str | None:
        pkg = path / "package.json"
        if pkg.exists():
            try:
                data = json.loads(pkg.read_text())
                scripts = data.get("scripts", {})
                if "test" in scripts:
                    return "npm test"
            except (json.JSONDecodeError, KeyError):
                pass
        return None

    def _detect_typescript(self, path: Path) -> str | None:
        return self._detect_javascript(path)

    def _detect_go(self, path: Path) -> str | None:
        if (path / "go.mod").exists():
            return "go test ./..."
        return None

    def _detect_ruby(self, path: Path) -> str | None:
        if (path / "Gemfile").exists():
            gemfile = (path / "Gemfile").read_text()
            if "rspec" in gemfile:
                return "bundle exec rspec"
            return "bundle exec rake test"
        if (path / "Rakefile").exists():
            return "rake test"
        return None

    def _detect_java(self, path: Path) -> str | None:
        if (path / "pom.xml").exists():
            return "mvn test"
        if (path / "build.gradle").exists() or (path / "build.gradle.kts").exists():
            return "./gradlew test"
        return None
