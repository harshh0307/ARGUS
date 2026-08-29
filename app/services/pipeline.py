from __future__ import annotations

import io
import tarfile
import tempfile
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


@dataclass
class PipelineOutcome:
    pr_result: PRLoopResult | None
    impacts: list = field(default_factory=list)
    files: dict = field(default_factory=dict)
    merged: bool = False
    merge_error: str | None = None
    steps: list = field(default_factory=list)

    @property
    def had_impacts(self) -> bool:
        return bool(self.impacts)


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


def scan_changes(
    settings: Settings,
    vendor_slug: str,
    root: Path,
    languages: list[str] | None = None,
) -> list:
    detection = detect_changes(settings, vendor_slug)
    lang_set = set(languages) if languages else None
    usages = ApiScanner(base_url=settings.api_base_url, languages=lang_set).scan(root)
    return assess_impact(usages, detection["changes"])


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
    outcome = PipelineOutcome(pr_result=None, impacts=impacts)
    if not impacts:
        return outcome
    model = build_suggestion_model(settings, vendor_slug=vendor_slug)
    max_attempts = max_attempts or settings.fix_max_attempts
    if dry_run:
        contents: dict[Path, str] = {}
        for impact in impacts:
            path = root / impact.usage.file
            if path not in contents:
                contents[path] = path.read_text(encoding="utf-8-sig")
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
) -> PipelineOutcome:
    vendor_guidance = _vendor_guidance(settings, vendor_slug)
    client = GitHubClient(token=settings.github_token)
    info = client.get_repo_info(owner, repo)
    if info is None:
        raise ValueError(f"repo {owner}/{repo} not found")
    base = base or info["default_branch"]

    with tempfile.TemporaryDirectory() as tmp:
        if local_dir:
            root = Path(local_dir)
        else:
            root = Path(tmp) / "checkout"
            root.mkdir(parents=True)
            _extract_tarball(client.repo_tarball(owner, repo, base), root)

        impacts = scan_changes(settings, vendor_slug, root, languages=languages)
        outcome = PipelineOutcome(pr_result=None, impacts=impacts)
        if not impacts:
            return outcome

        files: dict[str, str] = {}
        for impact in impacts:
            if impact.usage.file not in files:
                files[impact.usage.file] = (root / impact.usage.file).read_text(encoding="utf-8-sig")
        outcome.files = files

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

        model = build_suggestion_model(settings, vendor_slug=vendor_slug)
        body = build_pr_body(
            pr_body_summary
            or f"Argus found {len(impacts)} breaking API change(s) in this repo.",
            pr_body_details
            or [f"{i.change.method.upper()} {i.change.path}: {i.change.detail}" for i in impacts],
        )
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
        return outcome