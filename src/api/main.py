# src/api/main.py
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.api.schemas import NewsItemOut
from src.classification.prompt import CATEGORIES
from src.collectors.sources_config import load_sources_config
from src.config import get_settings
from src.db.models import NewsItem
from src.db.repository import sync_sources
from src.db.session import SessionLocal, get_session
from src.review.schemas import FeedbackIn
from src.review.service import ItemNotFoundError, submit_feedback
from src.scheduler import add_classification_job, add_scoring_job, build_scheduler
from src.scoring.prompt import PRIORITIES


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    sources = load_sources_config(settings.sources_config_path)
    sync_session = SessionLocal()
    try:
        sync_sources(sync_session, sources)
    finally:
        sync_session.close()
    scheduler = build_scheduler(sources, SessionLocal)
    add_classification_job(
        scheduler,
        SessionLocal,
        batch_size=settings.classification_batch_size,
        interval_minutes=settings.classification_interval_minutes,
        max_attempts=settings.classification_max_attempts,
    )
    add_scoring_job(
        scheduler,
        SessionLocal,
        batch_size=settings.scoring_batch_size,
        interval_minutes=settings.scoring_interval_minutes,
        max_attempts=settings.scoring_max_attempts,
    )
    scheduler.start()
    app.state.scheduler = scheduler
    yield
    scheduler.shutdown()


app = FastAPI(title="Touch-Go News", lifespan=lifespan)

_VIEW_TO_PRIORITY = {
    "a_voir": "A",
    "a_surveiller": "B",
    "faible_priorite": "C",
}

_SINCE_TO_DELTA = {
    "24h": timedelta(hours=24),
    "3d": timedelta(days=3),
    "7d": timedelta(days=7),
}


def _filtered_items(
    session: Session,
    priority: str | None,
    category: str | None,
    since: str | None,
    view: str | None,
) -> list[NewsItem]:
    if priority is not None and priority not in PRIORITIES:
        raise HTTPException(status_code=422, detail=f"invalid priority: {priority!r}")
    if category is not None and category not in CATEGORIES:
        raise HTTPException(status_code=422, detail=f"invalid category: {category!r}")

    effective_priority = priority or _VIEW_TO_PRIORITY.get(view)

    query = select(NewsItem).order_by(NewsItem.detected_at.desc())
    if effective_priority is not None:
        query = query.where(NewsItem.priority == effective_priority)
    if category is not None:
        query = query.where(NewsItem.primary_category == category)
    if since is not None:
        cutoff = datetime.now(timezone.utc) - _SINCE_TO_DELTA[since]
        query = query.where(NewsItem.detected_at >= cutoff)

    return list(session.execute(query).scalars())


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/items", response_model=list[NewsItemOut])
def list_items(
    priority: str | None = None,
    category: str | None = None,
    since: str | None = None,
    view: str | None = None,
    session: Session = Depends(get_session),
) -> list[NewsItem]:
    return _filtered_items(session, priority, category, since, view)


@app.post("/items/{item_id}/feedback", response_model=NewsItemOut)
def submit_item_feedback(
    item_id: int, feedback: FeedbackIn, session: Session = Depends(get_session)
) -> NewsItem:
    try:
        return submit_feedback(session, item_id, feedback)
    except ItemNotFoundError:
        raise HTTPException(status_code=404, detail="item not found") from None
