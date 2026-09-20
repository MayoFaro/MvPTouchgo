import pytest

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
