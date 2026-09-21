import logging
from dataclasses import dataclass

import anthropic
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.classification.client import classify_item
from src.config import get_settings
from src.db.models import NewsItem

logger = logging.getLogger(__name__)


@dataclass
class ClassificationJobResult:
    classified: int
    failed: int


async def classify_pending_items(session: Session, batch_size: int) -> ClassificationJobResult:
    pending = (
        session.execute(
            select(NewsItem)
            .where(NewsItem.primary_category.is_(None))
            .order_by(NewsItem.detected_at.asc())
            .limit(batch_size)
        )
        .scalars()
        .all()
    )

    classified = 0
    failed = 0

    if not pending:
        return ClassificationJobResult(classified=classified, failed=failed)

    async with anthropic.AsyncAnthropic(api_key=get_settings().anthropic_api_key) as client:
        for item in pending:
            try:
                result = await classify_item(item.original_title, item.original_text, client=client)
            except Exception:  # noqa: BLE001 - a single item must never break the whole batch
                # A failure mid-item (classification or a DB error from a prior
                # commit) can leave the session in "rollback required" state:
                # roll back first, otherwise the next iteration's commit fails too.
                session.rollback()
                logger.exception("Classification failed for item %s", item.id)
                failed += 1
                continue
            item.primary_category = result.primary_category
            item.secondary_categories = result.secondary_categories
            item.classification_confidence = result.classification_confidence
            item.model_reason = result.reasoning
            session.commit()
            classified += 1
    return ClassificationJobResult(classified=classified, failed=failed)
