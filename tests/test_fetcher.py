import httpx
import pytest

from app.core.config import Settings
from app.ingestion.fetcher import SpecFetcher, SpecFetchError


def make_settings(**overrides) -> Settings:
    defaults = {"http_max_retries": 2, "http_backoff_base_seconds": 0.01}
    defaults.update(overrides)
    return Settings(**defaults)


def test_fetch_returns_parsed_json_and_etag():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["If-None-Match"] == '"abc"'
        return httpx.Response(200, json={"paths": {}}, headers={"ETag": '"def"'})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    fetcher = SpecFetcher(make_settings(), client=client)

    result = fetcher.fetch("https://example.com/spec.json", etag='"abc"')

    assert result is not None
    assert result.content == {"paths": {}}
    assert result.etag == '"def"'


def test_fetch_returns_none_on_304():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(304)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    fetcher = SpecFetcher(make_settings(), client=client)

    assert fetcher.fetch("https://example.com/spec.json", etag='"abc"') is None


def test_fetch_retries_then_raises_on_transport_error():
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        raise httpx.ConnectError("boom")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    fetcher = SpecFetcher(make_settings(), client=client)

    with pytest.raises(SpecFetchError):
        fetcher.fetch("https://example.com/spec.json")
    assert attempts["n"] == 2


def test_fetch_raises_on_unexpected_status():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    fetcher = SpecFetcher(make_settings(), client=client)

    with pytest.raises(SpecFetchError):
        fetcher.fetch("https://example.com/spec.json")
