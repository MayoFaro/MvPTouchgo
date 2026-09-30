import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from src.collectors.base import Collector, RawItem
from src.collectors.sources_config import SourceConfig
from src.config import get_settings
from src.db.repository import save_raw_items, update_source_run_status

logger = logging.getLogger(__name__)


@dataclass
class CollectionResult:
    source_id: str
    ok: bool
    inserted: int = 0
    skipped_duplicates: int = 0
    skipped_stale: int = 0
    error: str | None = None


def filter_recent_items(items: list[RawItem], max_age_days: int) -> tuple[list[RawItem], int]:
    """Drop items whose ``published_at`` is older than ``max_age_days``.

    Items without a ``published_at`` (some collectors, e.g. BEA and PPRuNe,
    have no reliable date field) are always kept: we cannot tell whether
    they are stale, so we err on the side of showing them.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    kept: list[RawItem] = []
    skipped = 0
    for item in items:
        if item.published_at is not None and item.published_at < cutoff:
            skipped += 1
            continue
        kept.append(item)
    return kept, skipped


async def run_collection(
    session: Session, source_config: SourceConfig, collector: Collector
) -> CollectionResult:
    try:
        items = await collector.fetch()
        recent_items, skipped_stale = filter_recent_items(
            items, get_settings().max_item_age_days
        )
        result = save_raw_items(session, source_config.id, recent_items)
        update_source_run_status(session, source_config.id, status="OK")
        return CollectionResult(
            source_id=source_config.id,
            ok=True,
            inserted=result.inserted,
            skipped_duplicates=result.skipped_duplicates,
            skipped_stale=skipped_stale,
        )
    except Exception as exc:  # noqa: BLE001 - a single source must never break the others
        # A DB-originated failure leaves the session in "rollback required" state:
        # roll back first, otherwise the status update below cannot succeed.
        session.rollback()
        logger.exception("Collection failed for source %s", source_config.id)
        try:
            update_source_run_status(session, source_config.id, status="FAILED", error=str(exc))
        except Exception as status_exc:  # noqa: BLE001 - status recording must not break isolation
            logger.exception(
                "Failed to record run status for source %s after collection failure", source_config.id
            )
        return CollectionResult(source_id=source_config.id, ok=False, error=str(exc))
