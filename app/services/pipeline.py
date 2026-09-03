from __future__ import annotations

import io
import logging
import tarfile
import tempfile
import time
from contextlib import chdir
from dataclasses import dataclass, field
from pathlib import Path

from app.core.config import Settings
from app.detection.detect import run_detection
from app.fix.agent import build_suggestion_model, fix_impact_on_content, run_fix
from app.github.client import GitHubApiError, GitHubClient
from app.github.pr import PRLoopResult, build_pr_body, run_pr_loop
from app.scan.impact import assess_impact
from app.scan.scanner import ApiScanner

logger = logging.getLogger(__name__)


def _create_pipeline_run(settings: Settings, repository_id: int) -> object | None:
    """Create a PipelineRun record in the database. Returns the row or None."""
    if not settings.database_url:
        return None
    try:
        from app.db.models import PipelineRun
        from app.db.repository import open_session

        session = open_session(settings)
        try:
            row = PipelineRun(repository_id=repository_id, status="running")
            session.add(row)
            session.commit()
            session.refresh(row)
            return row
        finally:
            session.close()
    except Exception:
        logger.exception("Failed to create PipelineRun record")
        return None


def _update_pipeline_run(
    settings: Settings,
    pipeline_run_id: int,
    *,
    status: str | None = None,
    current_step: str | None = None,
    pr_number: int | None = None,
    pr_url: str | None = None,
    error_message: str | None = None,
) -> None:
    """Update a PipelineRun record."""
    if not settings.database_url:
        return
    try:
        from app.db.models import PipelineRun
        from app.db.repository import open_session

        session = open_session(settings)
        try:
            row = session.get(PipelineRun, pipeline_run_id)
            if row is None:
                return
            from datetime import UTC, datetime

            if status:
                row.status = status
            if current_step is not None:
                row.current_step = current_step
            if status == "running" and row.started_at is None:
                row.started_at = datetime.now(UTC)
            if status in ("success", "failed"):
                row.completed_at = datetime.now(UTC)
                row.current_step = None
            if pr_number is not None:
                row.pr_number = pr_number
            if pr_url is not None:
                row.pr_url = pr_url
            if error_message is not None:
                row.error_message = error_message
            session.commit()
        finally:
            session.close()
    except Exception:
        logger.exception("Failed to update PipelineRun %d", pipeline_run_id)


@dataclass
class PipelineOutcome:
    pr_result: PRLoopResult | None
    impacts: list = field(default_factory=list)
    files: dict = field(default_factory=dict)
    merged: bool = False
    merge_error: str | None = None
    steps: list = field(default_factory=list)
    # Rollback support
    _original_contents: dict[str, str] = field(default_factory=dict, repr=False)
    # Telemetry
    started_at: float = field(default_factory=time.time, repr=False)
    completed_at: float | None = None
    vendor_slug: str = ""
    duration_seconds: float | None = None

    @property
    def had_impacts(self) -> bool:
        return bool(self.impacts)

    def record_completion(self) -> None:
        """Record completion time and duration."""
        self.completed_at = time.time()
        self.duration_seconds = self.completed_at - self.started_at

    def rollback(self, root: Path) -> int:
        """Revert all changes to original contents. Returns number of files reverted."""
        reverted = 0
        for file_path, original_content in self._original_contents.items():
            full_path = root / file_path
            if full_path.exists():
                full_path.write_text(original_content, encoding="utf-8")
                reverted += 1
        return reverted


def detect_changes(settings: Settings, vendor_slug: str = "github") -> dict:
    return run_detection(settings, vendor_slug=vendor_slug)


def _extract_tarball(data: bytes, dest: Path) -> None:
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


def _sort_impacts(impacts: list) -> list:
    """Sort impacts by file and line to avoid conflicts during fixing.

    Order: alphabetically by file, then by line number descending (bottom-up)
    so that fixing later lines doesn't shift line numbers of earlier fixes.
    """
    return sorted(impacts, key=lambda i: (i.usage.file, -i.usage.line))


def _retry_with_backoff(func, max_retries: int = 3, base_delay: float = 1.0):
    """Execute a function with exponential backoff retry."""
    last_error = None
    for attempt in range(max_retries):
        try:
            return func()
        except GitHubApiError as e:
            last_error = e
            if "rate limit" in str(e).lower() or "429" in str(e):
                delay = base_delay * (2 ** attempt)
                logger.warning(f"Rate limited, retrying in {delay}s (attempt {attempt + 1}/{max_retries})")
                time.sleep(delay)
            else:
                raise
    raise last_error


def scan_changes(
    settings: Settings,
    vendor_slug: str,
    root: Path,
    languages: list[str] | None = None,
) -> list:
    detection = detect_changes(settings, vendor_slug)
    lang_set = set(languages) if languages else None
    scanner = ApiScanner(base_url=settings.api_base_url, languages=lang_set)
    usages, headers, bodies, auths, responses = scanner.scan(root)
    impacts = assess_impact(usages, headers, bodies, auths, responses, detection["changes"])
    # Sort impacts to avoid conflicts during fixing
    return _sort_impacts(impacts)


def _vendor_guidance(settings: Settings, vendor_slug: str) -> str | None:
    try:
        from app.registry.vendors import get_vendor

        return get_vendor(settings, vendor_slug).fix_guidance
    except (ValueError, AttributeError):
        return None


def fix_directory(
    settings: Settings,
    root: Path,
    max_attempts: int | None = None,
    dry_run: bool = False,
    vendor_slug: str = "github",
    languages: list[str] | None = None,
) -> PipelineOutcome:
    vendor_guidance = _vendor_guidance(settings, vendor_slug)
    impacts = scan_changes(settings, vendor_slug, root, languages=languages)
    outcome = PipelineOutcome(pr_result=None, impacts=impacts, vendor_slug=vendor_slug)
    if not impacts:
        outcome.record_completion()
        return outcome
    model = build_suggestion_model(settings, vendor_slug=vendor_slug)
    max_attempts = max_attempts or settings.fix_max_attempts
    if dry_run:
        contents: dict[Path, str] = {}
        for impact in impacts:
            path = root / impact.usage.file
            if path not in contents:
                contents[path] = path.read_text(encoding="utf-8-sig")
            # Store original content for rollback
            if impact.usage.file not in outcome._original_contents:
                outcome._original_contents[impact.usage.file] = contents[path]
            patched, err = fix_impact_on_content(
                impact,
                impact.usage.file,
                contents[path],
                model,
                max_attempts=max_attempts,
                base_url=settings.api_base_url,
                vendor_guidance=vendor_guidance,
            )
            outcome.steps.append(
                {
                    "file": impact.usage.file,
                    "line": impact.usage.line,
                    "ok": patched is not None,
                    "err": err,
                    "before": contents[path],
                    "after": patched,
                }
            )
            if patched is not None:
                contents[path] = patched
        outcome.record_completion()
        return outcome
    with chdir(root):
        results = run_fix(
            impacts,
            model,
            max_attempts,
            base_url=settings.api_base_url,
            vendor_guidance=vendor_guidance,
        )
    outcome.steps = results
    outcome.record_completion()
    return outcome


def run_repo_pipeline(
    settings: Settings,
    owner: str,
    repo: str,
    *,
    base: str | None = None,
    branch: str = "argus/fix",
    local_dir: Path | None = None,
    max_attempts: int | None = None,
    check_timeout: float | None = None,
    merge: bool = False,
    pr_body_summary: str | None = None,
    pr_body_details: list[str] | None = None,
    vendor_slug: str = "github",
    languages: list[str] | None = None,
    run_tests: bool = False,
    test_command: str | None = None,
    repository_id: int | None = None,
) -> PipelineOutcome:
    # Create pipeline run record
    pipeline_run = None
    if repository_id is not None:
        pipeline_run = _create_pipeline_run(settings, repository_id)
    try:
        return _run_repo_pipeline_inner(
            settings, owner, repo,
            base=base, branch=branch, local_dir=local_dir,
            max_attempts=max_attempts, check_timeout=check_timeout,
            merge=merge, pr_body_summary=pr_body_summary,
            pr_body_details=pr_body_details, vendor_slug=vendor_slug,
            languages=languages, run_tests=run_tests, test_command=test_command,
            pipeline_run=pipeline_run,
        )
    except Exception as exc:
        if pipeline_run is not None:
            _update_pipeline_run(
                settings, pipeline_run.id,
                status="failed", error_message=str(exc)[:500],
            )
        raise


def _run_repo_pipeline_inner(
    settings: Settings,
    owner: str,
    repo: str,
    *,
    base: str | None = None,
    branch: str = "argus/fix",
    local_dir: Path | None = None,
    max_attempts: int | None = None,
    check_timeout: float | None = None,
    merge: bool = False,
    pr_body_summary: str | None = None,
    pr_body_details: list[str] | None = None,
    vendor_slug: str = "github",
    languages: list[str] | None = None,
    run_tests: bool = False,
    test_command: str | None = None,
    pipeline_run: object | None = None,
) -> PipelineOutcome:
    vendor_guidance = _vendor_guidance(settings, vendor_slug)
    client = GitHubClient(token=settings.github_token)

    def _step(name: str) -> None:
        if pipeline_run is not None:
            _update_pipeline_run(settings, pipeline_run.id, current_step=name)

    _step("downloading")
    def _get_repo_info():
        return client.get_repo_info(owner, repo)

    info = _retry_with_backoff(_get_repo_info)
    if info is None:
        raise ValueError(f"repo {owner}/{repo} not found")
    base = base or info["default_branch"]

    with tempfile.TemporaryDirectory() as tmp:
        if local_dir:
            root = Path(local_dir)
        else:
            root = Path(tmp) / "checkout"
            root.mkdir(parent=True)
            _extract_tarball(client.repo_tarball(owner, repo, base), root)

        _step("scanning")
        impacts = scan_changes(settings, vendor_slug, root, languages=languages)
        outcome = PipelineOutcome(pr_result=None, impacts=impacts, vendor_slug=vendor_slug)
        if not impacts:
            outcome.record_completion()
            return outcome

        files: dict[str, str] = {}
        for impact in impacts:
            if impact.usage.file not in files:
                files[impact.usage.file] = (root / impact.usage.file).read_text(encoding="utf-8-sig")
        outcome.files = files

        # Store original contents for rollback
        outcome._original_contents = dict(files)

        try:
            stale = client.find_open_pull(owner, repo, branch)
            if stale is not None:
                client.close_pull(owner, repo, stale)
        except GitHubApiError:
            pass
        try:
            if client.get_ref(owner, repo, branch) is not None:
                client.delete_branch(owner, repo, branch)
        except GitHubApiError:
            pass

        _step("fixing")
        model = build_suggestion_model(settings, vendor_slug=vendor_slug)
        body = build_pr_body(
            pr_body_summary
            or f"Argus found {len(impacts)} breaking API change(s) in this repo.",
            pr_body_details
            or [f"{i.change.method.upper()} {i.change.path}: {i.change.detail}" for i in impacts],
        )

        # Run local tests before PR if requested
        if run_tests and test_command:
            import subprocess

            logger.info(f"Running local tests: {test_command}")
            try:
                result = subprocess.run(
                    test_command,
                    shell=True,
                    cwd=str(root),
                    capture_output=True,
                    text=True,
                    timeout=300,
                    check=False,
                )
                if result.returncode != 0:
                    logger.warning(f"Local tests failed: {result.stderr[:500]}")
                    outcome.record_completion()
                    return outcome
                logger.info("Local tests passed")
            except subprocess.TimeoutExpired:
                logger.warning("Local tests timed out")
                outcome.record_completion()
                return outcome

        _step("pushing")
        result: PRLoopResult = run_pr_loop(
            client,
            owner,
            repo,
            base=base,
            branch=branch,
            files=files,
            impacts=impacts,
            suggestion_model=model,
            max_attempts=max_attempts or settings.fix_max_attempts,
            check_timeout=check_timeout or 600.0,
            check_interval=15.0,
            base_url=settings.api_base_url,
            body=body,
            vendor_guidance=vendor_guidance,
        )
        outcome.pr_result = result
        if pipeline_run is not None:
            pr_url = f"https://github.com/{owner}/{repo}/pull/{result.pr_number}" if result.pr_number else None
            _update_pipeline_run(
                settings, pipeline_run.id,
                status="success" if result.passed else "failed",
                pr_number=result.pr_number,
                pr_url=pr_url,
                error_message=result.error if not result.passed else None,
            )
        if merge and result.passed:
            try:
                client.merge_pull_request(owner, repo, result.pr_number)
                outcome.merged = True
            except GitHubApiError as exc:
                outcome.merge_error = str(exc)
        outcome.record_completion()
        return outcome
