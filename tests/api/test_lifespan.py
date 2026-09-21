"""Exercise the FastAPI startup path (lifespan -> source sync -> scheduler)."""

import textwrap

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from src.api import main as api_main
from src.config import get_settings
from src.db.models import NewsSource


@pytest.fixture()
def empty_sources_config(tmp_path, monkeypatch):
    """Point the app at a config with no active sources, so startup stays offline."""
    config_path = tmp_path / "sources.yaml"
    config_path.write_text(
        textwrap.dedent(
            """
            sources:
              - id: disabled-source
                name: Disabled Source
                type: rss
                url: https://example.invalid/feed
                language: fr
                source_type: press
                poll_interval_minutes: 30
                active: false
            """
        )
    )
    monkeypatch.setenv("SOURCES_CONFIG_PATH", str(config_path))
    get_settings.cache_clear()
    yield config_path
    get_settings.cache_clear()


@pytest.fixture()
def api_session_factory(engine, monkeypatch):
    """Keep lifespan's own session on the test database."""
    factory = sessionmaker(bind=engine, future=True, expire_on_commit=False, autoflush=False)
    monkeypatch.setattr(api_main, "SessionLocal", factory)
    yield factory
    with factory() as cleanup:
        cleanup.query(NewsSource).filter_by(id="disabled-source").delete()
        cleanup.commit()


def test_lifespan_starts_app_syncs_sources_and_serves_requests(
    empty_sources_config, api_session_factory
):
    # TestClient as a context manager is what actually runs lifespan.
    with TestClient(api_main.app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        assert client.app.state.scheduler.running is True
        # The only configured source is inactive, so the classification job
        # (always registered) is the sole scheduled job.
        job_ids = {job.id for job in client.app.state.scheduler.get_jobs()}
        assert job_ids == {"classification"}

        with api_session_factory() as session:
            source = session.get(NewsSource, "disabled-source")
            assert source is not None
            assert source.name == "Disabled Source"
            assert source.language == "fr"
            assert source.active is False
