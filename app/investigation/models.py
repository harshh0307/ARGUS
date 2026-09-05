from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ChangelogChunk:
    source_url: str
    title: str
    content: str
    published_at: datetime | None = None
    vendor_slug: str = ""


@dataclass
class SearchResult:
    content: str
    url: str
    score: float
    source: str  # "changelog" | "docs"


@dataclass
class InvestigationResult:
    vendor_slug: str
    alert_id: int
    changelog_snippets: list[str] = field(default_factory=list)
    doc_references: list[str] = field(default_factory=list)
    context_summary: str = ""
    confidence_score: float = 0.0
