from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.collectors.base import RawItem
from src.collectors.sources_config import SourceConfig
from src.db.models import NewsItem, NewsSource


@dataclass
class SaveResult:
    inserted: int
    skipped_duplicates: int


def sync_sources(session: Session, sources: list[SourceConfig]) -> None:
    """Upsert the configured sources into ``news_source``.

    Only the configuration-owned columns are written. The runner-owned columns
    (``last_run_at`` / ``last_run_status`` / ``last_run_error``) are never touched.
    """
    for config in sources:
        existing = session.get(NewsSource, config.id)
        if existing is None:
            session.add(
                NewsSource(
                    id=config.id,
                    name=config.name,
                    url=config.url,
                    source_type=config.source_type,
                    language=config.language,
                    active=config.active,
                )
            )
            continue
        existing.name = config.name
        existing.url = config.url
        existing.source_type = config.source_type
        existing.language = config.language
        existing.active = config.active
    session.commit()


def save_raw_items(session: Session, source_id: str, items: list[RawItem]) -> SaveResult:
    inserted = 0
    skipped = 0
    # Rows added during this call are not yet flushed (SessionLocal uses
    # autoflush=False), so the SELECT below cannot see them: track them here
    # to keep an in-batch duplicate from blowing up the whole commit.
    seen_in_batch: set[tuple[str, str]] = set()
    for item in items:
        key = (source_id, item.source_item_id)
        if key in seen_in_batch:
            skipped += 1
            continue
        already_exists = session.execute(
            select(NewsItem.id).where(
                NewsItem.source_id == source_id,
                NewsItem.source_item_id == item.source_item_id,
            )
        ).first()
        if already_exists:
            skipped += 1
            continue
        seen_in_batch.add(key)
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
