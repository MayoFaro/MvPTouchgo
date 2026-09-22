import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import anthropic
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.adaptive.examples import build_classification_examples
from src.classification.client import classify_item
from src.config import get_settings
from src.db.models import NewsItem

logger = logging.getLogger(__name__)


@dataclass
class ClassificationJobResult:
    classified: int
    failed: int


async def classify_pending_items(
    session: Session, batch_size: int, max_attempts: int
) -> ClassificationJobResult:
    pending = (
        session.execute(
            select(NewsItem)
            .where(
                NewsItem.primary_category.is_(None),
                NewsItem.classification_attempts < max_attempts,
            )
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

    settings = get_settings()
    examples = build_classification_examples(
        session, settings.adaptive_min_examples, settings.adaptive_max_examples
    )

    async with anthropic.AsyncAnthropic(api_key=get_settings().anthropic_api_key) as client:
        for item in pending:
            try:
                result = await classify_item(
                    item.original_title, item.original_text, examples=examples, client=client
                )
            except Exception as exc:  # noqa: BLE001 - a single item must never break the whole batch
                # A failure mid-item (classification or a DB error from a prior
                # commit) can leave the session in "rollback required" state:
                # roll back first, otherwise the next iteration's commit fails too.
                session.rollback()
                try:
                    item.classification_attempts += 1
                    errors = list((item.model_metadata or {}).get("classification_errors", []))
                    errors.append(
                        {
                            "attempt": item.classification_attempts,
                            "at": datetime.now(timezone.utc).isoformat(),
                            "error": f"{type(exc).__name__}: {exc}"[:500],
                        }
                    )
                    item.model_metadata = {
                        **(item.model_metadata or {}),
                        "classification_errors": errors,
                    }
                    session.commit()
                    if item.classification_attempts >= max_attempts:
                        logger.warning(
                            "Item %s exhausted classification attempts (%d/%d)",
                            item.id,
                            item.classification_attempts,
                            max_attempts,
                        )
                except Exception:  # noqa: BLE001 - recording the failure must not itself break isolation
                    logger.exception(
                        "Failed to record classification failure bookkeeping for item %s", item.id
                    )
                    session.rollback()
                logger.exception("Classification failed for item %s", item.id)
                failed += 1
                continue
            try:
                item.primary_category = result.primary_category
                item.secondary_categories = result.secondary_categories
                item.classification_confidence = result.classification_confidence
                item.model_reason = result.reasoning
                session.commit()
                classified += 1
            except Exception as exc:  # noqa: BLE001 - a single item must never break the whole batch
                # Persisting a successful classification is itself a DB write that can
                # fail (constraint violation, transient connection error, ...). Roll
                # back first so the session isn't left in "rollback required" state
                # for the next iteration's commit.
                session.rollback()
                try:
                    item.classification_attempts += 1
                    errors = list((item.model_metadata or {}).get("classification_errors", []))
                    errors.append(
                        {
                            "attempt": item.classification_attempts,
                            "at": datetime.now(timezone.utc).isoformat(),
                            "error": f"{type(exc).__name__}: {exc}"[:500],
                        }
                    )
                    item.model_metadata = {
                        **(item.model_metadata or {}),
                        "classification_errors": errors,
                    }
                    session.commit()
                    if item.classification_attempts >= max_attempts:
                        logger.warning(
                            "Item %s exhausted classification attempts (%d/%d)",
                            item.id,
                            item.classification_attempts,
                            max_attempts,
                        )
                except Exception:  # noqa: BLE001 - recording the failure must not itself break isolation
                    logger.exception(
                        "Failed to record classification failure bookkeeping for item %s", item.id
                    )
                    session.rollback()
                logger.exception("Committing classification result failed for item %s", item.id)
                failed += 1
                continue
    return ClassificationJobResult(classified=classified, failed=failed)
