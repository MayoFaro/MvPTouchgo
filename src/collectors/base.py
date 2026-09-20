from abc import ABC, abstractmethod
from datetime import datetime

from pydantic import BaseModel


class RawItem(BaseModel):
    source_item_id: str
    canonical_url: str
    original_url: str
    original_title: str
    original_text: str
    language: str
    author: str | None = None
    published_at: datetime | None = None
    raw_metadata: dict = {}


class Collector(ABC):
    def __init__(self, source_id: str):
        self.source_id = source_id

    @abstractmethod
    async def fetch(self) -> list[RawItem]:
        ...
