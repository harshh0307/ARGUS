from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.db.models import Base


@lru_cache(maxsize=4)
def get_engine(url: str) -> Engine:
    if url.startswith("sqlite:///"):
        path = url.removeprefix("sqlite:///")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    kwargs = {"echo": False}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(url, **kwargs)


def init_db(engine: Engine | None = None) -> None:
    engine = engine or get_engine(_database_url())
    _create_all_locked(engine)


def _create_all_locked(engine: Engine) -> None:
    if engine.url.get_backend_name() == "postgresql":
        with engine.begin() as conn:
            conn.execute(text("SELECT pg_advisory_lock(724_201_01)"))
            try:
                Base.metadata.create_all(engine)
            finally:
                conn.execute(text("SELECT pg_advisory_unlock(724_201_01)"))
    else:
        Base.metadata.create_all(engine)


def session_factory(engine: Engine | None = None):
    engine = engine or get_engine(_database_url())
    return sessionmaker(bind=engine, expire_on_commit=False)


def _database_url(settings: Settings | None = None) -> str:
    settings = settings or Settings()
    if not settings.database_url:
        raise RuntimeError(
            "DATABASE_URL is not set; configure it in .env "
            "(e.g. sqlite:///data/argus.db or postgresql+psycopg://...)"
        )
    return settings.database_url