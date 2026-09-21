# src/api/main.py
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.api.schemas import NewsItemOut
from src.collectors.sources_config import load_sources_config
from src.config import get_settings
from src.db.models import NewsItem
from src.db.repository import sync_sources
from src.db.session import SessionLocal, get_session
from src.scheduler import add_classification_job, build_scheduler


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
    scheduler.start()
    app.state.scheduler = scheduler
    yield
    scheduler.shutdown()


app = FastAPI(title="Touch-Go News", lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/items", response_model=list[NewsItemOut])
def list_items(session: Session = Depends(get_session)) -> list[NewsItem]:
    return list(
        session.execute(select(NewsItem).order_by(NewsItem.detected_at.desc())).scalars()
    )
