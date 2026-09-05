from __future__ import annotations

import logging
import time
from pathlib import Path

from app.core.config import Settings
from app.validation.models import TestResult

logger = logging.getLogger(__name__)

DOCKER_IMAGES = {
    "python": "python:3.12-slim",
    "javascript": "node:22-slim",
    "typescript": "node:22-slim",
    "go": "golang:1.22-alpine",
    "ruby": "ruby:3.3-slim",
    "java": "eclipse-temurin:21-jre",
    "php": "php:8.3-cli",
    "csharp": "mcr.microsoft.com/dotnet/sdk:8.0",
}


class Sandbox:
    """Docker-based sandbox for running tests in isolation."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                import docker
                self._client = docker.from_env()
            except Exception as exc:
                raise RuntimeError(f"Docker is not available: {exc}") from exc
        return self._client

    def run_tests(
        self,
        repo_path: Path,
        test_command: str,
        language: str,
    ) -> TestResult:
        client = self._get_client()
        image = DOCKER_IMAGES.get(language, "python:3.12-slim")

        try:
            client.images.pull(image)
        except Exception:
            logger.warning("could not pull image %s, using local", image)

        start = time.monotonic()
        container = None
        try:
            container = client.containers.run(
                image,
                command=["sh", "-c", test_command],
                volumes={str(repo_path.resolve()): {"bind": "/workspace", "mode": "rw"}},
                working_dir="/workspace",
                mem_limit=self.settings.validation_memory_limit,
                network_disabled=True,
                detach=True,
                remove=False,
            )

            result = container.wait(timeout=self.settings.validation_timeout_seconds)
            logs = container.logs(stdout=True, stderr=True).decode("utf-8", errors="replace")
            duration = time.monotonic() - start

            return TestResult(
                passed=result.get("StatusCode", 1) == 0,
                exit_code=result.get("StatusCode", 1),
                output=logs,
                duration_seconds=duration,
            )
        except Exception as exc:
            duration = time.monotonic() - start
            return TestResult(
                passed=False,
                exit_code=-1,
                output=str(exc),
                duration_seconds=duration,
            )
        finally:
            if container is not None:
                try:
                    container.remove(force=True)
                except Exception:
                    pass
