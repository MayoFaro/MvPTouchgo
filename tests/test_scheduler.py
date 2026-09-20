from src.collectors.sources_config import SourceConfig
from src.scheduler import build_scheduler


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
