
from fastapi.testclient import TestClient

from app.api.main import create_app
from app.core.config import Settings
from app.db.engine import get_engine, init_db, session_factory
from app.db.models import Vendor
from app.db.repository import (
    record_changelog_entries,
    search_changelog,
    set_default_engine,
)
from app.search.embeddings import build_embedder, cosine_similarity, embed_text


def make_app(database_url=None, **overrides):
    defaults = {
        "database_url": database_url,
        "github_token": "pat-token",
        "api_base_url": "https://api.github.com",
        "github_app_id": None,
        "github_app_private_key": None,
        "github_install_id": None,
        "auth_secret_key": "test-secret-key-for-jwt",
        "auth_algorithm": "HS256",
        "access_token_expire_minutes": 30,
        "refresh_token_expire_days": 7,
    }
    defaults.update(overrides)
    return create_app(Settings(**defaults))


def register_and_login(client, email="test@example.com", password="secret123"):
    client.post("/api/v1/auth/register", json={"email": email, "password": password})
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def seeded_engine(tmp_path):
    url = f"sqlite:///{tmp_path / 'search.db'}"
    engine = get_engine(url)
    init_db(engine)
    set_default_engine(engine)
    return engine


def session_of(engine):
    return session_factory(engine)()


def seed_changelog(engine, vendor_slug="github", entries=None):
    session = session_of(engine)
    session.add(
        Vendor(slug=vendor_slug, name=vendor_slug)
    )
    session.commit()
    if entries:
        record_changelog_entries(session, vendor_slug, entries, embedder=None)
        session.commit()
    session.close()


def test_embed_text_joins_parts():
    text = embed_text("breaking", "/users/{id}", "get", "returns 404 now")
    assert text == "breaking | get | /users/{id} | returns 404 now"


def test_cosine_similarity():
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0
    assert abs(cosine_similarity([1.0, 2.0, 3.0], [4.0, 5.0, 6.0]) - 0.974) < 0.01
    assert cosine_similarity([], [1.0]) == 0.0


def test_record_changelog_entries_without_embedder(tmp_path):
    engine = seeded_engine(tmp_path)
    entries = [
        {"title": "Breaking: /users/{id}", "content": "GET endpoint removed", "source_url": "https://example.com/1"},
    ]
    session = session_of(engine)
    rows = record_changelog_entries(session, "github", entries, embedder=None)
    session.commit()
    assert len(rows) == 1
    assert rows[0].title == "Breaking: /users/{id}"
    assert rows[0].embedding is None
    session.close()


def test_record_changelog_entries_with_embedder(tmp_path):
    engine = seeded_engine(tmp_path)
    entries = [
        {"title": "Breaking: /users/{id}", "content": "GET endpoint removed", "source_url": "https://example.com/1"},
        {"title": "Additive: /orgs", "content": "POST endpoint added", "source_url": "https://example.com/2"},
    ]
    fake = lambda texts: [[float(i)] for i in range(len(texts))]
    session = session_of(engine)
    rows = record_changelog_entries(session, "github", entries, embedder=fake)
    session.commit()
    assert [r.embedding for r in rows] == [[0.0], [1.0]]
    session.close()


def test_search_keyword_fallback(tmp_path):
    engine = seeded_engine(tmp_path)
    entries = [
        {"title": "Breaking: /users/{id}", "content": "GET endpoint renamed", "source_url": "https://example.com/1"},
        {"title": "Additive: /orgs", "content": "POST endpoint create org", "source_url": "https://example.com/2"},
    ]
    session = session_of(engine)
    record_changelog_entries(session, "github", entries, embedder=None)
    session.commit()
    hits = search_changelog(session, "create org", vendor_slug="github", limit=10)
    assert len(hits) == 1
    assert hits[0][0].title == "Additive: /orgs"
    assert hits[0][1] == 2.0
    session.close()


def test_search_embeddings_rank_first(tmp_path):
    engine = seeded_engine(tmp_path)
    entries = [
        {"title": "Breaking: /users/{id}", "content": "GET endpoint changed", "source_url": "https://example.com/1"},
        {"title": "Additive: /orgs", "content": "POST endpoint added", "source_url": "https://example.com/2"},
    ]
    fake = lambda texts: [[1.0, 0.0] for _ in texts]
    session = session_of(engine)
    record_changelog_entries(session, "github", entries, embedder=fake)
    session.commit()
    query_embedder = lambda texts: [[1.0, 0.0] for _ in texts]
    hits = search_changelog(
        session, "something", vendor_slug="github", limit=10, embedder=query_embedder
    )
    assert len(hits) == 2
    assert all(abs(score - 1.0) < 1e-9 for _, score in hits)
    session.close()


def test_build_embedder_none_without_key():
    settings = Settings(embedding_api_key=None, embedding_base_url=None)
    assert build_embedder(settings) is None


def test_build_embedder_failure_falls_back(tmp_path):
    settings = Settings(
        embedding_api_key="sk-test",
        embedding_base_url="http://127.0.0.1:1/v1",
    )
    embedder = build_embedder(settings)
    assert embedder is not None
    assert embedder(["hello"]) is None


def test_api_search_endpoint(tmp_path):
    engine = seeded_engine(tmp_path)
    session = session_of(engine)
    session.add(Vendor(slug="github", name="GitHub"))
    session.commit()
    entries = [
        {"title": "Breaking: /repos/{owner}/{repo}", "content": "DELETE endpoint removed", "source_url": "https://example.com/1"},
    ]
    record_changelog_entries(session, "github", entries, embedder=None)
    session.commit()
    session.close()

    client = TestClient(
        make_app(database_url=engine.url.render_as_string(hide_password=False))
    )
    headers = register_and_login(client)
    response = client.get("/api/v1/search/changelog", params={"q": "delete repo", "vendor": "github"}, headers=headers)
    assert response.status_code == 200
    hits = response.json()
    assert len(hits) == 1
    assert hits[0]["score"] > 0


def test_api_search_empty_query_returns_empty(tmp_path):
    engine = seeded_engine(tmp_path)
    client = TestClient(
        make_app(database_url=engine.url.render_as_string(hide_password=False))
    )
    headers = register_and_login(client)
    assert client.get("/api/v1/search/changelog", params={"q": ""}, headers=headers).json() == []
