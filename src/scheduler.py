import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.classification.job import classify_pending_items
from src.collectors.factory import build_collector
from src.collectors.runner import run_collection
from src.collectors.sources_config import SourceConfig
from src.db.repository import update_source_run_status

logger = logging.getLogger(__name__)


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
            # Fire once right away instead of waiting a full poll interval.
            next_run_time=datetime.now(timezone.utc),
        )
    return scheduler


async def _run_source_job(source: SourceConfig, session_factory) -> None:
    session = session_factory()
    try:
        # build_collector() is inside the guarded block so that a bad `type:` in
        # the source config is isolated exactly like any other collector failure.
        collector = build_collector(source)
        await run_collection(session, source, collector)
    except Exception as exc:  # noqa: BLE001 - a single source must never break the others
        session.rollback()
        logger.exception("Could not run collection job for source %s", source.id)
        try:
            update_source_run_status(session, source.id, status="FAILED", error=str(exc))
        except Exception:  # noqa: BLE001 - status recording must not break isolation
            logger.exception("Failed to record run status for source %s", source.id)
    finally:
        session.close()


def add_classification_job(
    scheduler: AsyncIOScheduler,
    session_factory,
    batch_size: int,
    interval_minutes: int,
) -> None:
    scheduler.add_job(
        _classify_job,
        "interval",
        minutes=interval_minutes,
        id="classification",
        args=[session_factory, batch_size],
        # Fire once right away instead of waiting a full poll interval.
        next_run_time=datetime.now(timezone.utc),
    )


async def _classify_job(session_factory, batch_size: int) -> None:
    session = session_factory()
    try:
        await classify_pending_items(session, batch_size)
    except Exception:  # noqa: BLE001 - the classification job must never crash the scheduler
        logger.exception("Classification job failed")
    finally:
        session.close()
