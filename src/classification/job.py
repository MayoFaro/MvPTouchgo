import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.classification.client import ClassificationError, classify_item
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
    for item in pending:
        try:
            result = await classify_item(item.original_title, item.original_text)
        except ClassificationError:
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
