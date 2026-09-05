from __future__ import annotations

import logging

from app.core.config import Settings
from app.investigation.models import ChangelogChunk, SearchResult
from app.registry.vendors import Vendor
from app.search.embeddings import build_embedder, cosine_similarity

logger = logging.getLogger(__name__)


class DocSearcher:
    """RAG search against vendor documentation and changelogs."""

    def __init__(self, vendor: Vendor, settings: Settings):
        self.vendor = vendor
        self.settings = settings
        self._embedder = build_embedder(settings)

    def search(
        self,
        drift_details: dict,
        stored_chunks: list[ChangelogChunk] | None = None,
        top_k: int = 5,
    ) -> list[SearchResult]:
        query = self._build_query(drift_details)
        results: list[SearchResult] = []

        if stored_chunks and self._embedder:
            results = self._embedding_search(query, stored_chunks, top_k)

        if not results or (results and results[0].score < 0.5):
            keyword_results = self._keyword_search(query, stored_chunks or [], top_k)
            seen = {r.content[:100] for r in results}
            for kr in keyword_results:
                if kr.content[:100] not in seen:
                    results.append(kr)

        if self.vendor.docs_url and len(results) < top_k:
            doc_results = self._search_vendor_docs(drift_details, top_k - len(results))
            results.extend(doc_results)

        return results[:top_k]

    def _build_query(self, drift_details: dict) -> str:
        parts = []
        if "endpoint" in drift_details:
            parts.append(drift_details["endpoint"])
        if "details" in drift_details:
            details = drift_details["details"]
            if "removed_fields" in details:
                parts.append("removed " + " ".join(details["removed_fields"]))
            if "type_changes" in details:
                for tc in details["type_changes"]:
                    parts.append(f"{tc.get('field', '')} type changed")
        if not parts:
            parts.append("API change")
        return " ".join(parts)

    def _embedding_search(
        self, query: str, chunks: list[ChangelogChunk], top_k: int
    ) -> list[SearchResult]:
        if not self._embedder or not chunks:
            return []
        try:
            query_vec = self._embedder([query])[0]
        except Exception:  # noqa: BLE001
            return []

        scored = []
        for chunk in chunks:
            if chunk.embedding is not None:
                try:
                    sim = cosine_similarity(query_vec, chunk.embedding)
                    scored.append(SearchResult(
                        content=chunk.content,
                        url=chunk.source_url,
                        score=sim,
                        source="changelog",
                    ))
                except Exception:  # noqa: BLE001, S110
                    pass

        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:top_k]

    def _keyword_search(
        self, query: str, chunks: list[ChangelogChunk], top_k: int
    ) -> list[SearchResult]:
        terms = [t.lower() for t in query.split() if len(t) > 2]
        if not terms or not chunks:
            return []

        scored = []
        for chunk in chunks:
            haystack = (chunk.title + " " + chunk.content).lower()
            score = sum(1.0 for t in terms if t in haystack)
            if score > 0:
                scored.append(SearchResult(
                    content=chunk.content,
                    url=chunk.source_url,
                    score=score / len(terms),
                    source="changelog",
                ))

        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:top_k]

    def _search_vendor_docs(self, drift_details: dict, top_k: int) -> list[SearchResult]:
        results = []
        docs_url = self.vendor.docs_url
        if not docs_url:
            return results

        endpoint = drift_details.get("endpoint", "")
        if endpoint:
            parts = endpoint.split()
            if len(parts) >= 2:
                path_parts = parts[1].strip("/").split("/")
                doc_path = "/".join(path_parts[:2])
                url = f"{docs_url.rstrip('/')}/{doc_path}"
                results.append(SearchResult(
                    content=f"Vendor documentation for {endpoint}",
                    url=url,
                    score=0.3,
                    source="docs",
                ))

        return results[:top_k]
