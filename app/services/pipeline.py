from __future__ import annotations

import io
import logging
import tarfile
import time
from contextlib import chdir
from dataclasses import dataclass, field
from pathlib import Path

from app.core.config import Settings
from app.fix.agent import build_suggestion_model, fix_impact_on_content, run_fix
from app.scan.impact import assess_impact
from app.scan.models import DriftSignal
from app.scan.scanner import ApiScanner

logger = logging.getLogger(__name__)


def _create_pipeline_run(settings: Settings, repository_id: int) -> object | None:
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
    pr_result: object | None = None
    impacts: list = field(default_factory=list)
    files: dict = field(default_factory=dict)
    merged: bool = False
    merge_error: str | None = None
    steps: list = field(default_factory=list)
    _original_contents: dict[str, str] = field(default_factory=dict, repr=False)
    started_at: float = field(default_factory=time.time, repr=False)
    completed_at: float | None = None
    vendor_slug: str = ""
    duration_seconds: float | None = None

    @property
    def had_impacts(self) -> bool:
        return bool(self.impacts)

    def record_completion(self) -> None:
        self.completed_at = time.time()
        self.duration_seconds = self.completed_at - self.started_at

    def rollback(self, root: Path) -> int:
        reverted = 0
        for file_path, original_content in self._original_contents.items():
            full_path = root / file_path
            if full_path.exists():
                full_path.write_text(original_content, encoding="utf-8")
                reverted += 1
        return reverted


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
    return sorted(impacts, key=lambda i: (i.usage.file, -i.usage.line))


def _vendor_guidance(settings: Settings, vendor_slug: str) -> str | None:
    try:
        from app.registry.vendors import get_vendor
        return get_vendor(settings, vendor_slug).fix_guidance
    except (ValueError, AttributeError):
        return None


def scan_changes(
    settings: Settings,
    vendor_slug: str,
    root: Path,
    languages: list[str] | None = None,
) -> list:
    lang_set = set(languages) if languages else None
    scanner = ApiScanner(base_url=settings.api_base_url, languages=lang_set)
    usages, headers, bodies, auths, responses = scanner.scan(root)
    drift_signals = _get_drift_signals(settings, vendor_slug)
    impacts = assess_impact(usages, headers, bodies, auths, responses, drift_signals)
    return _sort_impacts(impacts)


def _get_drift_signals(settings: Settings, vendor_slug: str) -> list[DriftSignal]:
    if not settings.database_url:
        return []
    try:
        from app.db.repository import list_open_drift_alerts, open_session
        session = open_session(settings)
        try:
            alerts = list_open_drift_alerts(session, vendor_slug=vendor_slug)
            return [
                DriftSignal(
                    kind=alert.alert_type,
                    severity=alert.severity,
                    path=alert.endpoint or "",
                    method="",
                    detail=str(alert.details),
                    old_value=alert.details,
                )
                for alert in alerts
            ]
        finally:
            session.close()
    except Exception:  # noqa: BLE001
        return []
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
    name: str,
    *,
    branch: str = "main",
    merge: bool = True,
    vendor_slug: str = "github",
    repository_id: int | None = None,
) -> PipelineOutcome:

    try:
        root = Path(".")
        impacts = scan_changes(settings, vendor_slug, root)
        outcome = PipelineOutcome(pr_result=None, impacts=impacts, vendor_slug=vendor_slug)
        if not impacts:
            outcome.record_completion()
            return outcome
        model = build_suggestion_model(settings, vendor_slug=vendor_slug)
        max_attempts = settings.fix_max_attempts
        guidance = _vendor_guidance(settings, vendor_slug)
        from app.github.client import GitHubClient
        client = GitHubClient(token=settings.github_token)
        client.get_repo_info(owner, name)
        branch = branch or "argus/fix"
        with chdir(root):
            results = run_fix(
                impacts,
                model,
                max_attempts,
                base_url=settings.api_base_url,
                vendor_guidance=guidance,
            )
        outcome.steps = results
        outcome.record_completion()
        return outcome
    except Exception:
        logger.exception("Pipeline failed")
        outcome = PipelineOutcome()
        outcome.record_completion()
        return outcome
