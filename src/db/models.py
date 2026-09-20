from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class NewsSource(Base):
    __tablename__ = "news_source"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    url: Mapped[str] = mapped_column(String, nullable=False)
    source_type: Mapped[str] = mapped_column(String, nullable=False)
    language: Mapped[str] = mapped_column(String, nullable=False)
    confirmation_level: Mapped[str | None] = mapped_column(String, nullable=True)
    detection_value: Mapped[str | None] = mapped_column(String, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_run_status: Mapped[str | None] = mapped_column(String, nullable=True)
    last_run_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class NewsItem(Base):
    __tablename__ = "news_item"
    __table_args__ = (
        UniqueConstraint("source_id", "source_item_id", name="uq_news_item_source_item"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("news_source.id"), nullable=False)
    source_item_id: Mapped[str] = mapped_column(String, nullable=False)
    canonical_url: Mapped[str] = mapped_column(String, nullable=False)
    original_url: Mapped[str] = mapped_column(String, nullable=False)
    original_title: Mapped[str] = mapped_column(Text, nullable=False)
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str | None] = mapped_column(String, nullable=True)
    author: Mapped[str | None] = mapped_column(String, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    primary_category: Mapped[str | None] = mapped_column(String, nullable=True)
    secondary_categories: Mapped[list | None] = mapped_column(JSON, nullable=True)
    classification_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    country: Mapped[str | None] = mapped_column(String, nullable=True)
    region: Mapped[str | None] = mapped_column(String, nullable=True)
    entities: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    touchgo_interest: Mapped[int | None] = mapped_column(Integer, nullable=True)
    event_importance: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_confidence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    urgency: Mapped[int | None] = mapped_column(Integer, nullable=True)

    priority: Mapped[str | None] = mapped_column(String, nullable=True)
    verification_status: Mapped[str | None] = mapped_column(String, nullable=True)

    duplicate_of: Mapped[int | None] = mapped_column(ForeignKey("news_item.id"), nullable=True)
    event_id: Mapped[int | None] = mapped_column(ForeignKey("news_event.id"), nullable=True)

    status: Mapped[str] = mapped_column(String, default="NEW", nullable=False)

    model_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    human_decision: Mapped[str | None] = mapped_column(String, nullable=True)
    human_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    human_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewer_id: Mapped[str | None] = mapped_column(String, nullable=True)


class NewsEvent(Base):
    __tablename__ = "news_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str | None] = mapped_column(String, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    importance: Mapped[int | None] = mapped_column(Integer, nullable=True)
    verification_status: Mapped[str | None] = mapped_column(String, nullable=True)
    summary_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class NewsFeedback(Base):
    __tablename__ = "news_feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    news_item_id: Mapped[int] = mapped_column(ForeignKey("news_item.id"), nullable=False)
    decision: Mapped[str] = mapped_column(String, nullable=False)
    reason: Mapped[str | None] = mapped_column(String, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    previous_priority: Mapped[str | None] = mapped_column(String, nullable=True)
    previous_category: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    reviewer_id: Mapped[str | None] = mapped_column(String, nullable=True)
