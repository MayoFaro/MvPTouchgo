import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from src.collectors.base import Collector
from src.collectors.sources_config import SourceConfig
from src.db.repository import save_raw_items, update_source_run_status

logger = logging.getLogger(__name__)


@dataclass
class CollectionResult:
    source_id: str
    ok: bool
    inserted: int = 0
    skipped_duplicates: int = 0
    error: str | None = None


async def run_collection(
    session: Session, source_config: SourceConfig, collector: Collector
) -> CollectionResult:
    try:
        items = await collector.fetch()
        result = save_raw_items(session, source_config.id, items)
        update_source_run_status(session, source_config.id, status="OK")
        return CollectionResult(
            source_id=source_config.id,
            ok=True,
            inserted=result.inserted,
            skipped_duplicates=result.skipped_duplicates,
        )
    except Exception as exc:  # noqa: BLE001 - a single source must never break the others
        logger.exception("Collection failed for source %s", source_config.id)
        try:
            update_source_run_status(session, source_config.id, status="FAILED", error=str(exc))
        except Exception as status_exc:  # noqa: BLE001 - status recording must not break isolation
            logger.exception(
                "Failed to record run status for source %s after collection failure", source_config.id
            )
        return CollectionResult(source_id=source_config.id, ok=False, error=str(exc))
