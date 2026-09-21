import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from src.db.base import Base
from src.db.models import NewsSource  # noqa: F401 ensures metadata is populated

TEST_DATABASE_URL = "postgresql+psycopg://touchgo:touchgo@localhost:5432/touchgo_news_test"

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _run_migrations() -> None:
    """Build the test schema with the real Alembic migration chain.

    ``alembic/env.py`` reads the URL from ``get_settings()``, so the target
    database is selected through the ``DATABASE_URL`` environment variable.
    """
    env = {**os.environ, "DATABASE_URL": TEST_DATABASE_URL}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"alembic upgrade head failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(TEST_DATABASE_URL, future=True)
    Base.metadata.drop_all(eng)
    with eng.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS alembic_version"))
    _run_migrations()
    # Guard against the DATABASE_URL override silently not taking effect.
    tables = set(inspect(eng).get_table_names())
    missing = {"news_source", "news_item", "news_event", "news_feedback"} - tables
    if missing:
        raise RuntimeError(f"Alembic migration did not create the test schema; missing: {missing}")
    yield eng
    eng.dispose()


@pytest.fixture()
def db_session(engine):
    # join_transaction_mode="create_savepoint" is SQLAlchemy 2.0's supported way to
    # join a Session into an externally managed transaction: the Session works inside
    # a SAVEPOINT, so its commits never consume the outer transaction (which used to
    # trigger "transaction already deassociated from connection" at teardown).
    # autoflush=False mirrors SessionLocal's production configuration.
    connection = engine.connect()
    transaction = connection.begin()
    session_factory = sessionmaker(
        bind=connection,
        future=True,
        expire_on_commit=False,
        autoflush=False,
        join_transaction_mode="create_savepoint",
    )
    session = session_factory()
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture()
def make_source(db_session):
    def _make(source_id: str = "test-source", **overrides) -> NewsSource:
        # Check if source already exists to support multiple calls with the same ID
        existing = db_session.get(NewsSource, source_id)
        if existing:
            return existing

        source = NewsSource(
            id=source_id,
            name=overrides.get("name", "Test Source"),
            url=overrides.get("url", "https://example.com/feed"),
            source_type=overrides.get("source_type", "press"),
            language=overrides.get("language", "en"),
            active=overrides.get("active", True),
        )
        db_session.add(source)
        db_session.commit()
        return source

    return _make
