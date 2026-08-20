from fastapi.testclient import TestClient

from app.api.main import create_app
from app.core.config import Settings
from app.db.engine import get_engine, init_db, session_factory
from app.db.models import ChangelogEntry, DetectionRun, Vendor
from app.db.repository import (
    record_changelog_entries,
    search_changelog,
    set_default_engine,
)
from app.search.embeddings import cosine_similarity


def seeded_engine(tmp_path):
    url = f"sqlite:///{tmp_path / 'search-edge.db'}"
    engine = get_engine(url)
    init_db(engine)
    set_default_engine(engine)
    return engine


def make_app(database_url=None, **overrides):
    defaults = {
        "database_url": database_url,
        "github_token": "pat-token",
        "api_base_url": "https://api.github.com",
        "github_app_id": None,
        "github_app_private_key": None,
        "github_install_id": None,
    }
    defaults.update(overrides)
    return create_app(Settings(**defaults))


def seed_entries(engine, count=3, vendor_slug="github", embedder=None):
    session = session_factory(engine)()
    session.add(Vendor(slug=vendor_slug, name=vendor_slug, spec_url="https://s"))
    run = DetectionRun(
        vendor_slug=vendor_slug,
        new_digest="abc",
        breaking_count=count,
        changes=[
            {
                "kind": "breaking",
                "path": f"/items/{i}",
                "method": "delete",
                "detail": f"detail number {i}",
            }
            for i in range(count)
        ],
    )
    session.add(run)
    session.flush()
    record_changelog_entries(session, vendor_slug, run, run.changes, embedder=embedder)
    session.commit()
    session.close()
    return run


def test_cosine_similarity_zero_vector():
    assert cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0
    assert cosine_similarity([1.0, 0.0], [0.0, 0.0]) == 0.0


def test_cosine_similarity_dimension_mismatch():
    assert cosine_similarity([1.0, 0.0], [1.0]) == 0.0
    assert cosine_similarity([], []) == 0.0


def test_cosine_similarity_negative_components():
    value = cosine_similarity([1.0, -1.0], [-1.0, 1.0])
    assert value == -1.0 or abs(value - (-1.0)) < 1e-9


def test_record_changelog_entries_empty_changes(tmp_path):
    engine = seeded_engine(tmp_path)
    session = session_factory(engine)()
    session.add(Vendor(slug="github", name="GitHub", spec_url="https://s"))
    run = DetectionRun(vendor_slug="github", new_digest="a", changes=[])
    session.add(run)
    session.flush()
    rows = record_changelog_entries(session, "github", run, [], embedder=None)
    session.commit()
    assert rows == []
    assert session.query(ChangelogEntry).count() == 0
    session.close()


def test_search_vendor_filter_no_match(tmp_path):
    engine = seeded_engine(tmp_path)
    seed_entries(engine, count=2, vendor_slug="github")
    session = session_factory(engine)()
    hits = search_changelog(session, "detail", vendor_slug="stripe", limit=10)
    assert hits == []
    session.close()


def test_search_limit_truncates_results(tmp_path):
    engine = seeded_engine(tmp_path)
    seed_entries(engine, count=3)
    session = session_factory(engine)()
    hits = search_changelog(session, "number", vendor_slug="github", limit=2)
    assert len(hits) == 2
    session.close()


def test_search_falls_back_to_keyword_when_embedder_fails(tmp_path):
    engine = seeded_engine(tmp_path)
    seed_entries(engine, count=2)
    session = session_factory(engine)()

    def broken_embedder(texts):
        return None

    hits = search_changelog(
        session, "detail number 1", vendor_slug="github", limit=10, embedder=broken_embedder
    )
    assert len(hits) >= 1
    assert hits[0][0].path == "/items/1"
    session.close()


def test_search_zero_query_vector_returns_ranked_zero_scores(tmp_path):
    engine = seeded_engine(tmp_path)
    fake = lambda texts: [[1.0, 0.0] for _ in texts]
    seed_entries(engine, count=2, embedder=fake)
    session = session_factory(engine)()

    zero_embedder = lambda texts: [[0.0, 0.0] for _ in texts]
    hits = search_changelog(
        session, "irrelevant", vendor_slug="github", limit=10, embedder=zero_embedder
    )
    assert len(hits) == 2
    assert all(score == 0.0 for _, score in hits)
    session.close()


def test_search_no_embedding_rows_with_embedder_uses_keyword(tmp_path):
    engine = seeded_engine(tmp_path)
    session = session_factory(engine)()
    session.add(Vendor(slug="github", name="GitHub", spec_url="https://s"))
    run = DetectionRun(
        vendor_slug="github",
        new_digest="a",
        changes=[{"kind": "breaking", "path": "/kw", "method": "get", "detail": "keyword hit"}],
    )
    session.add(run)
    session.flush()
    record_changelog_entries(session, "github", run, run.changes, embedder=None)
    session.commit()

    embedder = lambda texts: [[1.0, 0.0] for _ in texts]
    hits = search_changelog(session, "keyword", vendor_slug="github", limit=10, embedder=embedder)
    assert len(hits) == 1
    assert hits[0][0].path == "/kw"
    assert hits[0][1] == 1.0
    session.close()


def test_search_case_insensitive_keywords(tmp_path):
    engine = seeded_engine(tmp_path)
    seed_entries(engine, count=1)
    session = session_factory(engine)()
    hits = search_changelog(session, "DETAIL NUMBER 0", vendor_slug="github", limit=10)
    assert len(hits) == 1
    session.close()


def test_api_search_vendor_filter_and_limit(tmp_path):
    engine = seeded_engine(tmp_path)
    seed_entries(engine, count=3)
    client = TestClient(
        make_app(database_url=engine.url.render_as_string(hide_password=False))
    )
    response = client.get(
        "/api/v1/search/changelog",
        params={"q": "number", "vendor": "github", "limit": 2},
    )
    assert response.status_code == 200
    assert len(response.json()) == 2

    empty = client.get("/api/v1/search/changelog", params={"q": "number", "vendor": "stripe"})
    assert empty.json() == []


def test_api_search_orders_by_score_desc(tmp_path):
    engine = seeded_engine(tmp_path)
    seed_entries(engine, count=3)
    client = TestClient(
        make_app(database_url=engine.url.render_as_string(hide_password=False))
    )
    response = client.get("/api/v1/search/changelog", params={"q": "detail"})
    hits = response.json()
    scores = [h["score"] for h in hits]
    assert scores == sorted(scores, reverse=True)
    assert all(h["kind"] == "breaking" for h in hits)