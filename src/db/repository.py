from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.collectors.base import RawItem
from src.db.models import NewsItem, NewsSource


@dataclass
class SaveResult:
    inserted: int
    skipped_duplicates: int


def save_raw_items(session: Session, source_id: str, items: list[RawItem]) -> SaveResult:
    inserted = 0
    skipped = 0
    for item in items:
        already_exists = session.execute(
            select(NewsItem.id).where(
                NewsItem.source_id == source_id,
                NewsItem.source_item_id == item.source_item_id,
            )
        ).first()
        if already_exists:
            skipped += 1
            continue
        session.add(
            NewsItem(
                source_id=source_id,
                source_item_id=item.source_item_id,
                canonical_url=item.canonical_url,
                original_url=item.original_url,
                original_title=item.original_title,
                original_text=item.original_text,
                language=item.language or None,
                author=item.author,
                published_at=item.published_at,
                status="NEW",
            )
        )
        inserted += 1
    session.commit()
    return SaveResult(inserted=inserted, skipped_duplicates=skipped)


def update_source_run_status(
    session: Session, source_id: str, status: str, error: str | None = None
) -> None:
    source = session.get(NewsSource, source_id)
    if source is None:
        return
    source.last_run_at = datetime.now(timezone.utc)
    source.last_run_status = status
    source.last_run_error = error
    session.commit()
