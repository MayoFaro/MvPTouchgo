from datetime import datetime, timezone

from sqlalchemy.orm import Session

from src.config import get_settings
from src.db.models import NewsFeedback, NewsItem
from src.review.schemas import FeedbackIn


class ItemNotFoundError(Exception):
    """Raised when submit_feedback targets a NewsItem id that doesn't exist."""


def submit_feedback(session: Session, item_id: int, feedback: FeedbackIn) -> NewsItem:
    item = session.get(NewsItem, item_id)
    if item is None:
        raise ItemNotFoundError(f"news item {item_id} not found")

    reviewer_id = feedback.reviewer_id or get_settings().default_reviewer_id
    # reason only carries meaning for REJETER; any value supplied alongside
    # another decision is not persisted (see design doc §3).
    reason = feedback.reason if feedback.decision == "REJETER" else None

    session.add(
        NewsFeedback(
            news_item_id=item.id,
            decision=feedback.decision,
            reason=reason,
            comment=feedback.comment,
            previous_priority=item.priority,
            previous_category=item.primary_category,
            reviewer_id=reviewer_id,
        )
    )

    item.human_decision = feedback.decision
    item.human_reason = reason
    item.human_comment = feedback.comment
    item.reviewed_at = datetime.now(timezone.utc)
    item.reviewer_id = reviewer_id

    session.commit()
    return item
