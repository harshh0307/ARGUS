from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path

from app.core.config import get_settings
from app.registry.vendors import list_vendors


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="argus",
        description="Argus - autonomous API drift detection and healing.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("vendors", help="list registered vendors")
    p.set_defaults(func=cmd_vendors)

    p = sub.add_parser("scan", help="scan a repo for API call sites")
    p.add_argument("dir", nargs="?", default=".", help="repo directory to scan")
    p.add_argument("--vendor", default="github", help="vendor slug")
    p.add_argument("--languages", nargs="+", help="languages to scan")
    p.set_defaults(func=cmd_scan)

    p = sub.add_parser("fix", help="generate and apply fixes for impacted call sites")
    p.add_argument("dir", nargs="?", default=".", help="repo directory to fix")
    p.add_argument("--vendor", default="github", help="vendor slug")
    p.add_argument("--languages", nargs="+", help="languages to scan")
    p.add_argument("--dry-run", action="store_true", help="print diffs without writing files")
    p.add_argument("--max-attempts", type=int, default=None, help="fix attempts per call site")
    p.set_defaults(func=cmd_fix)

    return parser


def cmd_vendors(args) -> int:
    settings = get_settings()
    for vendor in list_vendors(settings):
        state = "on" if vendor.enabled else "off"
        changelogs = len(vendor.changelog_urls)
        print(f"{vendor.slug:<15} {state:<3} changelogs={changelogs}  {vendor.base_api_url or ''}")
    return 0


def cmd_scan(args) -> int:
    from app.scan.scanner import ApiScanner

    settings = get_settings()
    root = Path(args.dir)
    languages = getattr(args, "languages", None)
    lang_set = set(languages) if languages else None
    scanner = ApiScanner(base_url=settings.api_base_url, languages=lang_set)
    usages, headers, bodies, auths, responses = scanner.scan(root)
    print(f"Scanned {args.dir}:")
    print(f"  Call sites: {len(usages)}")
    print(f"  Headers: {len(headers)}")
    print(f"  Body fields: {len(bodies)}")
    print(f"  Auth patterns: {len(auths)}")
    print(f"  Response handlers: {len(responses)}")
    return 0


def cmd_fix(args) -> int:
    settings = get_settings()
    root = Path(args.dir)
    languages = getattr(args, "languages", None)

    from app.services.pipeline import fix_directory

    vendor_slug = getattr(args, "vendor", "github")
    try:
        outcome = fix_directory(
            settings,
            root,
            max_attempts=args.max_attempts,
            dry_run=args.dry_run,
            vendor_slug=vendor_slug,
            languages=languages,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if not outcome.had_impacts:
        print("no impacted call sites")
        return 0

    if args.dry_run:
        for step in outcome.steps:
            if not step["ok"]:
                print(f"  {step['file']}:{step['line']} FAILED: {step['err']}")
            else:
                print(f"  {step['file']}:{step['line']} OK")
                diff = difflib.unified_diff(
                    step["before"].splitlines(), step["after"].splitlines(),
                    fromfile=step["file"], tofile=step["file"], lineterm="",
                )
                print("\n".join(diff))
    else:
        for result in outcome.steps:
            if result.success:
                print(f"  {result.file}:{result.line} OK")
            else:
                print(f"  {result.file}:{result.line} FAILED: {result.error}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130
    except Exception as exc:  # noqa: BLE001
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
