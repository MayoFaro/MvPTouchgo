from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.collectors.factory import build_collector
from src.collectors.runner import run_collection
from src.collectors.sources_config import SourceConfig


def build_scheduler(sources: list[SourceConfig], session_factory) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    for source in sources:
        if not source.active:
            continue
        scheduler.add_job(
            _run_source_job,
            "interval",
            minutes=source.poll_interval_minutes,
            id=source.id,
            args=[source, session_factory],
        )
    return scheduler


async def _run_source_job(source: SourceConfig, session_factory) -> None:
    collector = build_collector(source)
    session = session_factory()
    try:
        await run_collection(session, source, collector)
    finally:
        session.close()
