import pytest
from unittest.mock import patch

from sqlalchemy import text

from src.collectors.base import Collector, RawItem
from src.collectors.runner import run_collection
from src.collectors.sources_config import SourceConfig
from src.db.models import NewsItem, NewsSource


def _config(source_id: str = "s1") -> SourceConfig:
    return SourceConfig(
        id=source_id,
        name="Source",
        type="rss",
        url="https://example.com/feed",
        language="en",
        source_type="press",
        poll_interval_minutes=30,
    )


class _WorkingCollector(Collector):
    async def fetch(self) -> list[RawItem]:
        return [
            RawItem(
                source_item_id="1",
                canonical_url="https://example.com/1",
                original_url="https://example.com/1",
                original_title="Title",
                original_text="Body",
                language="en",
            )
        ]


class _AbortingTransactionCollector(Collector):
    """Provokes a real DB-level failure that leaves the transaction in aborted state."""

    def __init__(self, source_id: str, session):
        super().__init__(source_id)
        self._session = session

    async def fetch(self) -> list[RawItem]:
        self._session.execute(
            text(
                "INSERT INTO news_item "
                "(source_id, source_item_id, canonical_url, original_url, original_title,"
                " original_text, detected_at, status) "
                "VALUES ('does-not-exist', 'x', 'u', 'u', 't', 'b', now(), 'NEW')"
            )
        )
        return []


class _FailingCollector(Collector):
    async def fetch(self) -> list[RawItem]:
        raise httpx_timeout_error()


def httpx_timeout_error() -> Exception:
    import httpx

    return httpx.TimeoutException("timed out")


@pytest.mark.asyncio
async def test_run_collection_persists_items_and_marks_source_ok(db_session, make_source):
    make_source(source_id="s1")
    config = _config()

    result = await run_collection(db_session, config, _WorkingCollector(source_id="s1"))

    assert result.ok is True
    assert result.inserted == 1
    assert db_session.query(NewsItem).count() == 1
    source = db_session.get(NewsSource, "s1")
    assert source.last_run_status == "OK"


@pytest.mark.asyncio
async def test_run_collection_isolates_collector_failure(db_session, make_source):
    make_source(source_id="s1")
    config = _config()

    result = await run_collection(db_session, config, _FailingCollector(source_id="s1"))

    assert result.ok is False
    assert "timed out" in result.error
    assert db_session.query(NewsItem).count() == 0
    source = db_session.get(NewsSource, "s1")
    assert source.last_run_status == "FAILED"


@pytest.mark.asyncio
async def test_run_collection_rolls_back_aborted_transaction_before_recording_status(
    db_session, make_source
):
    """A DB-level failure must be rolled back so the FAILED status can still be written."""
    make_source(source_id="s1")
    config = _config()

    result = await run_collection(
        db_session, config, _AbortingTransactionCollector(source_id="s1", session=db_session)
    )

    assert result.ok is False
    source = db_session.get(NewsSource, "s1")
    assert source.last_run_status == "FAILED"
    # Read it back from the database, not just from the identity map.
    db_session.expire_all()
    assert db_session.get(NewsSource, "s1").last_run_status == "FAILED"


@pytest.mark.asyncio
async def test_run_collection_isolates_status_update_failure(db_session, make_source):
    """Test that a failure in update_source_run_status doesn't propagate out of run_collection."""
    make_source(source_id="s1")
    config = _config()

    # Simulate a scenario where update_source_run_status fails (e.g., session in broken state)
    with patch("src.collectors.runner.update_source_run_status") as mock_update_status:
        # First call (in success path) succeeds, subsequent calls (in error path) fail
        mock_update_status.side_effect = [
            None,  # Success path would use this (not reached in this test)
            RuntimeError("Session is broken"),  # Failure path hits this
        ]

        result = await run_collection(db_session, config, _FailingCollector(source_id="s1"))

    # The important assertion: even though update_source_run_status raised,
    # run_collection still returns a proper CollectionResult instead of propagating
    assert result.ok is False
    assert "timed out" in result.error
    assert result.source_id == "s1"
