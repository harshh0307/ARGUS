from __future__ import annotations

import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.core.config import Settings
from app.investigation.models import ChangelogChunk
from app.registry.vendors import Vendor

logger = logging.getLogger(__name__)


class ChangelogScraper:
    """Scrapes vendor changelogs and release notes."""

    def __init__(self, vendor: Vendor, settings: Settings):
        self.vendor = vendor
        self.settings = settings
        self._client = httpx.Client(
            timeout=30,
            headers={"User-Agent": "Argus/0.2 (API drift monitor)"},
            follow_redirects=True,
        )

    def scrape(self, max_age_days: int = 90) -> list[ChangelogChunk]:
        chunks: list[ChangelogChunk] = []

        for url in self.vendor.changelog_urls:
            try:
                raw = self._fetch_page(url)
                parsed = self._extract_content(raw, url)
                chunks.extend(parsed)
            except Exception:
                logger.warning("failed to scrape changelog: %s", url, exc_info=True)

        if self.vendor.rss_url:
            try:
                rss_chunks = self._scrape_rss(self.vendor.rss_url)
                chunks.extend(rss_chunks)
            except Exception:
                logger.warning("failed to scrape RSS: %s", self.vendor.rss_url, exc_info=True)

        cutoff = datetime.now(UTC) - timedelta(days=max_age_days)
        return [c for c in chunks if c.published_at is None or c.published_at > cutoff]

    def _fetch_page(self, url: str) -> str:
        resp = self._client.get(url)
        resp.raise_for_status()
        return resp.text

    def _extract_content(self, html: str, source_url: str) -> list[ChangelogChunk]:
        text = self._html_to_text(html)
        if not text.strip():
            return []

        sections = self._split_sections(text)
        chunks = []
        for title, body in sections:
            if len(body.strip()) > 50:
                chunks.append(
                    ChangelogChunk(
                        source_url=source_url,
                        title=title or source_url,
                        content=body.strip()[:2000],
                        vendor_slug=self.vendor.slug,
                    )
                )
        return chunks

    def _scrape_rss(self, rss_url: str) -> list[ChangelogChunk]:
        try:
            import feedparser
        except ImportError:
            return []

        raw = self._fetch_page(rss_url)
        feed = feedparser.parse(raw)
        chunks = []
        for entry in feed.entries[:50]:
            published = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                published = datetime(*entry.published_parsed[:6], tzinfo=UTC)
            chunks.append(
                ChangelogChunk(
                    source_url=entry.get("link", rss_url),
                    title=entry.get("title", ""),
                    content=entry.get("summary", "")[:2000],
                    published_at=published,
                    vendor_slug=self.vendor.slug,
                )
            )
        return chunks

    def _html_to_text(self, html: str) -> str:
        try:
            import trafilatura
            result = trafilatura.extract(html, include_comments=False, include_tables=False)
            return result or ""
        except ImportError:
            return self._regex_html_strip(html)

    def _regex_html_strip(self, html: str) -> str:
        text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _split_sections(self, text: str) -> list[tuple[str, str]]:
        lines = text.split("\n")
        sections: list[tuple[str, str]] = []
        current_title = ""
        current_body_lines: list[str] = []

        for line in lines:
            stripped = line.strip()
            if stripped and (
                stripped.startswith("#")
                or stripped.upper() == stripped
                and len(stripped) > 5
                and len(stripped) < 100
            ):
                if current_body_lines:
                    sections.append((current_title, "\n".join(current_body_lines)))
                current_title = stripped.lstrip("#").strip()
                current_body_lines = []
            else:
                current_body_lines.append(line)

        if current_body_lines:
            sections.append((current_title, "\n".join(current_body_lines)))

        if not sections and text.strip():
            sections.append(("", text[:2000]))

        return sections
