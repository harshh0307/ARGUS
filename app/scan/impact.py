from __future__ import annotations

from app.detection.models import BREAKING, Change
from app.scan.models import Impact, Usage


def assess_impact(usages: list[Usage], changes: list[Change]) -> list[Impact]:
    impacts: list[Impact] = []
    for usage in usages:
        for change in changes:
            if change.severity != BREAKING:
                continue
            if change.method == usage.method and match_path(usage.path, change.path):
                impacts.append(Impact(usage, change))
    return sorted(impacts, key=lambda i: (i.usage.file, i.usage.line, i.change.kind))


def match_path(code_path: str, spec_path: str) -> bool:
    code_segments = [s for s in code_path.split("/") if s]
    spec_segments = [s for s in spec_path.split("/") if s]
    if len(code_segments) != len(spec_segments):
        return False
    for code_seg, spec_seg in zip(code_segments, spec_segments):
        if spec_seg.startswith("{") and spec_seg.endswith("}"):
            continue
        if code_seg.startswith("{") and code_seg.endswith("}"):
            return False
        if code_seg != spec_seg:
            return False
    return True
