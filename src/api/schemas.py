# src/api/schemas.py
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NewsItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_id: str
    original_title: str
    original_url: str
    language: str | None
    published_at: datetime | None
    detected_at: datetime
    status: str
    primary_category: str | None
    secondary_categories: list[str] | None
    classification_confidence: float | None
    classification_attempts: int
    touchgo_interest: int | None
    event_importance: int | None
    source_confidence: int | None
    urgency: int | None
    priority: str | None
    duplicate_of: int | None
