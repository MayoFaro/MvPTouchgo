import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.db.base import Base
from src.db.models import NewsSource  # noqa: F401 ensures metadata is populated

TEST_DATABASE_URL = "postgresql+psycopg://touchgo:touchgo@localhost:5432/touchgo_news_test"


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(TEST_DATABASE_URL, future=True)
    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def db_session(engine):
    connection = engine.connect()
    transaction = connection.begin()
    session_factory = sessionmaker(bind=connection, future=True, expire_on_commit=False)
    session = session_factory()
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture()
def make_source(db_session):
    def _make(source_id: str = "test-source", **overrides) -> NewsSource:
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
