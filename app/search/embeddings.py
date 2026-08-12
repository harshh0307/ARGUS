from __future__ import annotations

import math
from collections.abc import Callable

import httpx

from app.core.config import Settings

Embedder = Callable[[list[str]], list[list[float]] | None]


def build_embedder(settings: Settings) -> Embedder | None:
    api_key = getattr(settings, "embedding_api_key", None)
    if not api_key:
        return None
    base_url = (
        getattr(settings, "embedding_base_url", None) or "https://api.openai.com/v1"
    ).rstrip("/")
    model = getattr(settings, "embedding_model", None) or "text-embedding-3-small"

    def embed(texts: list[str]) -> list[list[float]] | None:
        try:
            response = httpx.post(
                f"{base_url}/embeddings",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"model": model, "input": texts},
                timeout=60.0,
            )
            response.raise_for_status()
            payload = response.json()
            ranked = sorted(payload["data"], key=lambda item: item["index"])
            return [item["embedding"] for item in ranked]
        except Exception:  # noqa: BLE001 - embedding is best-effort
            return None

    return embed


def embed_text(kind: str, path: str, method: str, detail: str | None) -> str:
    parts = [kind, method, path]
    if detail:
        parts.append(detail)
    return " | ".join(parts)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)
