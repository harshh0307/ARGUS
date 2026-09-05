from app.db.engine import get_engine, init_db, session_factory
from app.db.models import Vendor


def test_models_create_and_query(tmp_path):
    url = f"sqlite:///{tmp_path / 'argus.db'}"
    engine = get_engine(url)
    init_db(engine)
    session = session_factory(engine)()

    session.add(Vendor(slug="github", name="GitHub REST API"))
    session.commit()

    assert session.get(Vendor, "github").name == "GitHub REST API"
    session.close()
