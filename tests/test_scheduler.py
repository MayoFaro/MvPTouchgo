from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
import respx

from src.collectors.sources_config import SourceConfig
from src.db.models import NewsItem, NewsSource
from src.scheduler import _run_source_job, build_scheduler

FEED = (Path(__file__).parent / "fixtures" / "sample_feed.xml").read_text()


def _config(source_id: str, active: bool = True, interval: int = 30) -> SourceConfig:
    return SourceConfig(
        id=source_id,
        name=source_id,
        type="rss",
        url="https://example.com/feed",
        language="en",
        source_type="press",
        poll_interval_minutes=interval,
        active=active,
    )


def test_build_scheduler_registers_one_job_per_active_source():
    sources = [_config("a"), _config("b", active=False), _config("c")]

    scheduler = build_scheduler(sources, session_factory=lambda: None)

    job_ids = {job.id for job in scheduler.get_jobs()}
    assert job_ids == {"a", "c"}


def test_build_scheduler_uses_configured_interval():
    sources = [_config("a", interval=45)]

    scheduler = build_scheduler(sources, session_factory=lambda: None)

    job = scheduler.get_job("a")
    assert job.trigger.interval.total_seconds() == 45 * 60


def test_build_scheduler_schedules_first_run_immediately():
    scheduler = build_scheduler([_config("a", interval=45)], session_factory=lambda: None)

    job = scheduler.get_job("a")
    assert job.next_run_time is not None
    # Immediately, not one poll interval away.
    assert job.next_run_time <= datetime.now(timezone.utc) + timedelta(seconds=5)


@pytest.mark.asyncio
@respx.mock
async def test_run_source_job_runs_a_full_collection_cycle(db_session, make_source):
    make_source(source_id="a", url="https://example.com/feed")
    respx.get("https://example.com/feed").mock(
        return_value=httpx.Response(200, text=FEED, headers={"content-type": "application/rss+xml"})
    )

    await _run_source_job(_config("a"), session_factory=lambda: db_session)

    assert db_session.query(NewsItem).count() == 2
    assert db_session.get(NewsSource, "a").last_run_status == "OK"


@pytest.mark.asyncio
async def test_run_source_job_isolates_unknown_collector_type(db_session, make_source):
    make_source(source_id="a")
    bad_config = _config("a").model_copy(update={"type": "carrier_pigeon"})

    # Must not raise out of the scheduled job.
    await _run_source_job(bad_config, session_factory=lambda: db_session)

    source = db_session.get(NewsSource, "a")
    assert source.last_run_status == "FAILED"
    assert "Unknown collector type" in source.last_run_error
