import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import anthropic
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.adaptive.examples import build_scoring_examples
from src.config import get_settings
from src.db.models import NewsItem, NewsSource
from src.scoring.client import score_item

logger = logging.getLogger(__name__)


@dataclass
class ScoringJobResult:
    scored: int
    failed: int


async def score_pending_items(
    session: Session, batch_size: int, max_attempts: int
) -> ScoringJobResult:
    pending = session.execute(
        select(NewsItem, NewsSource.source_type)
        .join(NewsSource, NewsItem.source_id == NewsSource.id)
        .where(
            NewsItem.primary_category.is_not(None),
            NewsItem.touchgo_interest.is_(None),
            NewsItem.scoring_attempts < max_attempts,
        )
        .order_by(NewsItem.detected_at.asc())
        .limit(batch_size)
    ).all()

    scored = 0
    failed = 0

    if not pending:
        return ScoringJobResult(scored=scored, failed=failed)

    settings = get_settings()
    examples = build_scoring_examples(
        session,
        min_examples=settings.adaptive_min_examples,
        max_examples=settings.adaptive_max_examples,
    )

    async with anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key) as client:
        for item, source_type in pending:
            try:
                result = await score_item(
                    item.original_title,
                    item.original_text,
                    source_type,
                    examples=examples,
                    client=client,
                )
            except Exception as exc:  # noqa: BLE001 - a single item must never break the whole batch
                # A failure mid-item (scoring or a DB error from a prior commit)
                # can leave the session in "rollback required" state: roll back
                # first, otherwise the next iteration's commit fails too.
                session.rollback()
                try:
                    item.scoring_attempts += 1
                    errors = list((item.model_metadata or {}).get("scoring_errors", []))
                    errors.append(
                        {
                            "attempt": item.scoring_attempts,
                            "at": datetime.now(timezone.utc).isoformat(),
                            "error": f"{type(exc).__name__}: {exc}"[:500],
                        }
                    )
                    item.model_metadata = {
                        **(item.model_metadata or {}),
                        "scoring_errors": errors,
                    }
                    session.commit()
                    if item.scoring_attempts >= max_attempts:
                        logger.warning(
                            "Item %s exhausted scoring attempts (%d/%d)",
                            item.id,
                            item.scoring_attempts,
                            max_attempts,
                        )
                except Exception:  # noqa: BLE001 - recording the failure must not itself break isolation
                    logger.exception(
                        "Failed to record scoring failure bookkeeping for item %s", item.id
                    )
                    session.rollback()
                logger.exception("Scoring failed for item %s", item.id)
                failed += 1
                continue
            try:
                item.touchgo_interest = result.touchgo_interest
                item.event_importance = result.event_importance
                item.source_confidence = result.source_confidence
                item.urgency = result.urgency
                item.priority = result.priority
                item.model_metadata = {
                    **(item.model_metadata or {}),
                    "scoring_reasoning": result.reasoning,
                }
                session.commit()
                scored += 1
            except Exception as exc:  # noqa: BLE001 - a single item must never break the whole batch
                # Persisting a successful score is itself a DB write that can fail
                # (constraint violation, transient connection error, ...). Roll back
                # first so the session isn't left in "rollback required" state for
                # the next iteration's commit.
                session.rollback()
                try:
                    item.scoring_attempts += 1
                    errors = list((item.model_metadata or {}).get("scoring_errors", []))
                    errors.append(
                        {
                            "attempt": item.scoring_attempts,
                            "at": datetime.now(timezone.utc).isoformat(),
                            "error": f"{type(exc).__name__}: {exc}"[:500],
                        }
                    )
                    item.model_metadata = {
                        **(item.model_metadata or {}),
                        "scoring_errors": errors,
                    }
                    session.commit()
                    if item.scoring_attempts >= max_attempts:
                        logger.warning(
                            "Item %s exhausted scoring attempts (%d/%d)",
                            item.id,
                            item.scoring_attempts,
                            max_attempts,
                        )
                except Exception:  # noqa: BLE001 - recording the failure must not itself break isolation
                    logger.exception(
                        "Failed to record scoring failure bookkeeping for item %s", item.id
                    )
                    session.rollback()
                logger.exception("Committing scoring result failed for item %s", item.id)
                failed += 1
                continue
    return ScoringJobResult(scored=scored, failed=failed)
