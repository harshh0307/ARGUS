"""Argus command line interface.

Usage:
  argus vendors                List registered spec vendors
  argus detect                 Detect breaking API changes in the watched spec
  argus scan [DIR]             Scan a repo for call sites hit by breaking changes
  argus fix [DIR]              Generate and apply LLM fixes for impacted call sites
  argus pr OWNER/REPO          Full pipeline: detect, scan, fix, open a self-healing PR
"""

from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path

from app.core.config import get_settings
from app.db.repository import persist_detection
from app.detection.models import ADDITIVE, BREAKING
from app.registry.vendors import get_vendor as registry_get_vendor
from app.registry.vendors import list_vendors
from app.services.pipeline import detect_changes, fix_directory, run_repo_pipeline, scan_changes


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="argus",
        description="Argus - the changelog that reads your codebase.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("vendors", help="list registered spec vendors")
    p.set_defaults(func=cmd_vendors)

    p = sub.add_parser("detect", help="detect breaking API changes in the watched spec")
    p.add_argument("--vendor", default="github", help="vendor slug (default: github)")
    p.set_defaults(func=cmd_detect)

    p = sub.add_parser("scan", help="scan a repo for call sites hit by breaking changes")
    p.add_argument("dir", nargs="?", default=".", help="repo directory to scan (default: .)")
    p.add_argument("--vendor", default="github", help="vendor slug (default: github)")
    p.set_defaults(func=cmd_scan)

    p = sub.add_parser("fix", help="generate and apply LLM fixes for impacted call sites")
    p.add_argument("dir", nargs="?", default=".", help="repo directory to fix (default: .)")
    p.add_argument("--dry-run", action="store_true", help="print diffs without writing files")
    p.add_argument("--max-attempts", type=int, default=None, help="fix attempts per call site")
    p.set_defaults(func=cmd_fix)

    p = sub.add_parser("pr", help="detect, scan, fix and open a self-healing PR")
    p.add_argument("repo", help="target repo as OWNER/REPO")
    p.add_argument("--dir", default=None, help="local checkout to scan (default: API tarball)")
    p.add_argument("--base", default=None, help="base branch (default: repo default branch)")
    p.add_argument("--branch", default="argus/fix", help="fix branch to create")
    p.add_argument("--max-attempts", type=int, default=None, help="CI feedback loop attempts")
    p.add_argument("--check-timeout", type=float, default=None, help="seconds to wait per check")
    p.add_argument("--merge", action="store_true", help="merge the PR when CI passes")
    p.set_defaults(func=cmd_pr)

    return parser


def _print_changes(changes: list) -> None:
    breaking = [c for c in changes if c.severity == BREAKING]
    additive = [c for c in changes if c.severity == ADDITIVE]
    for change in breaking:
        detail = f" - {change.detail}" if change.detail else ""
        print(f"  [{change.kind}] {change.method.upper()} {change.path}{detail}")
    print(f"{len(breaking)} breaking, {len(additive)} additive changes")


def cmd_vendors(args) -> int:
    for vendor in list_vendors(get_settings()):
        state = "on" if vendor.enabled else "off"
        print(f"{vendor.slug:<10} {state:<3} poll={vendor.poll_interval_seconds}s  {vendor.spec_url}")
    return 0


def cmd_detect(args) -> int:
    settings = get_settings()
    vendor_slug = getattr(args, "vendor", "github")
    try:
        detection = detect_changes(settings, vendor_slug)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if settings.database_url:
        persist_detection(settings, vendor_slug, detection, registry_get_vendor(settings, vendor_slug))
    if detection.get("baselined"):
        print(f"Argus baseline stored for {vendor_slug}; no diff to report yet")
        return 0
    print("Argus detected API changes in the watched spec:")
    _print_changes(detection["changes"])
    return 0


def cmd_scan(args) -> int:
    settings = get_settings()
    vendor_slug = getattr(args, "vendor", "github")
    root = Path(args.dir)
    impacts = scan_changes(settings, vendor_slug, root)
    print(f"Scanned {args.dir}: {len(impacts)} impacted by breaking changes")
    for impact in impacts:
        print(f"  {impact}")
    return 0


def _unified_diff(file: str, before: str, after: str) -> str:
    diff = difflib.unified_diff(
        before.splitlines(),
        after.splitlines(),
        fromfile=file,
        tofile=file,
        lineterm="",
    )
    return "\n".join(diff)


def cmd_fix(args) -> int:
    settings = get_settings()
    root = Path(args.dir)
    try:
        outcome = fix_directory(
            settings, root, max_attempts=args.max_attempts, dry_run=args.dry_run
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not outcome.had_impacts:
        print("no impacted call sites")
        return 0
    if args.dry_run:
        fixed_count = 0
        for step in outcome.steps:
            if not step["ok"]:
                print(f"  {step['file']}:{step['line']} FAILED: {step['err']}")
                continue
            fixed_count += 1
            print(f"  {step['file']}:{step['line']} OK")
            print(_unified_diff(str(root / step["file"]), step["before"], step["after"]))
        print(f"{fixed_count}/{len(outcome.steps)} fixed (dry run)")
        return 0
    fixed = sum(1 for r in outcome.steps if r.success)
    for result in outcome.steps:
        if result.success:
            print(f"  {result.file}:{result.line} OK")
        else:
            print(f"  {result.file}:{result.line} FAILED: {result.error}")
    print(f"{fixed}/{len(outcome.steps)} fixed")
    return 0


def cmd_pr(args) -> int:
    settings = get_settings()
    from app.github.app_auth import build_token_provider

    try:
        build_token_provider(settings)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    owner, sep, repo = args.repo.partition("/")
    if not sep or not repo:
        print(f"error: expected OWNER/REPO, got {args.repo!r}", file=sys.stderr)
        return 2
    try:
        outcome = run_repo_pipeline(
            settings,
            owner,
            repo,
            base=args.base,
            branch=args.branch,
            local_dir=Path(args.dir) if args.dir else None,
            max_attempts=args.max_attempts,
            check_timeout=args.check_timeout,
            merge=args.merge,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    result = outcome.pr_result
    if result is None:
        print("no impacted call sites; nothing to do")
        return 0
    print(f"PR #{result.pr_number}: {result.pr_url}")
    print(f"passed={result.passed} attempts={result.attempts}")
    if result.failure:
        print(f"last failure: {result.failure[:500]}")
    if outcome.merged:
        print("merged; fix branch deleted")
    elif outcome.merge_error:
        print(f"warning: merge rejected, PR left open: {outcome.merge_error}")
    return 0 if result.passed else 1


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130
    except Exception as exc:  # noqa: BLE001 - catch-all for unexpected failures
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())