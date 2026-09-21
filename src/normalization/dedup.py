from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.db.models import NewsItem
from src.normalization.text import normalize_text

SIMILARITY_THRESHOLD = 0.8
DATE_WINDOW = timedelta(hours=48)


def jaccard_similarity(a: str, b: str) -> float:
    tokens_a = set(a.split())
    tokens_b = set(b.split())
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)


def find_duplicate(
    session: Session,
    canonical_url: str,
    content_hash: str,
    original_title: str,
    reference_date: datetime,
) -> NewsItem | None:
    by_url = session.execute(
        select(NewsItem).where(NewsItem.canonical_url == canonical_url)
    ).scalars().first()
    if by_url is not None:
        return by_url

    by_hash = session.execute(
        select(NewsItem).where(NewsItem.content_hash == content_hash)
    ).scalars().first()
    if by_hash is not None:
        return by_hash

    normalized_title = normalize_text(original_title)
    window_start = reference_date - DATE_WINDOW
    window_end = reference_date + DATE_WINDOW
    effective_date = func.coalesce(NewsItem.published_at, NewsItem.detected_at)
    candidates = session.execute(
        select(NewsItem).where(
            effective_date >= window_start,
            effective_date <= window_end,
        )
    ).scalars().all()
    for candidate in candidates:
        candidate_title = normalize_text(candidate.original_title)
        if jaccard_similarity(normalized_title, candidate_title) >= SIMILARITY_THRESHOLD:
            return candidate
    return None
