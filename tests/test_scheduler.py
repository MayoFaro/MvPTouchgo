from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
import respx

import src.classification.job as job_module
import src.scheduler as scheduler_module
from src.classification.client import ClassificationResult
from src.collectors.sources_config import SourceConfig
from src.db.models import NewsItem, NewsSource
from src.scheduler import _classify_job, _run_source_job, add_classification_job, build_scheduler

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


def test_add_classification_job_registers_a_job_with_the_configured_interval():
    scheduler = build_scheduler([], session_factory=lambda: None)

    add_classification_job(
        scheduler,
        session_factory=lambda: None,
        batch_size=20,
        interval_minutes=3,
        max_attempts=5,
    )

    job = scheduler.get_job("classification")
    assert job is not None
    assert job.trigger.interval.total_seconds() == 3 * 60
    assert job.next_run_time is not None
    assert job.next_run_time <= datetime.now(timezone.utc) + timedelta(seconds=5)


@pytest.mark.asyncio
async def test_classify_job_runs_a_full_classification_cycle(db_session, make_source, monkeypatch):
    make_source(source_id="flightglobal")
    item = NewsItem(
        source_id="flightglobal",
        source_item_id="1",
        canonical_url="https://example.com/a",
        original_url="https://example.com/a",
        original_title="Airbus unveils new variant",
        original_text="Body",
    )
    db_session.add(item)
    db_session.commit()

    async def fake_classify_item(title, text, client=None):
        return ClassificationResult(
            primary_category="COMMERCIAL",
            secondary_categories=[],
            classification_confidence=0.7,
            reasoning="ok",
        )

    monkeypatch.setattr(job_module, "classify_item", fake_classify_item)

    await _classify_job(session_factory=lambda: db_session, batch_size=10, max_attempts=5)

    stored = db_session.get(NewsItem, item.id)
    assert stored.primary_category == "COMMERCIAL"


@pytest.mark.asyncio
async def test_classify_job_does_not_raise_on_unexpected_error(db_session, monkeypatch):
    async def broken_classify_pending_items(session, batch_size, max_attempts):
        raise RuntimeError("boom")

    monkeypatch.setattr(scheduler_module, "classify_pending_items", broken_classify_pending_items)

    # Must not raise out of the scheduled job.
    await _classify_job(session_factory=lambda: db_session, batch_size=10, max_attempts=5)


@pytest.mark.asyncio
async def test_classify_job_passes_max_attempts_through_to_classify_pending_items(
    db_session, monkeypatch
):
    received = {}

    async def spy_classify_pending_items(session, batch_size, max_attempts):
        received["batch_size"] = batch_size
        received["max_attempts"] = max_attempts
        return job_module.ClassificationJobResult(classified=0, failed=0)

    monkeypatch.setattr(scheduler_module, "classify_pending_items", spy_classify_pending_items)

    await _classify_job(session_factory=lambda: db_session, batch_size=7, max_attempts=2)

    assert received == {"batch_size": 7, "max_attempts": 2}
