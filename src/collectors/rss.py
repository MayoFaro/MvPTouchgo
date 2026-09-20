import logging
from datetime import datetime, timezone

import feedparser
import httpx

from src.collectors.base import Collector, RawItem

logger = logging.getLogger(__name__)

_HEADERS = {"User-Agent": "TouchGoNewsBot/0.1 (+https://touch-go.example)"}


class RSSCollector(Collector):
    def __init__(
        self,
        source_id: str,
        feed_url: str,
        http_client: httpx.AsyncClient | None = None,
        default_language: str = "",
    ):
        super().__init__(source_id)
        self.feed_url = feed_url
        self._http_client = http_client
        self.default_language = default_language

    async def fetch(self) -> list[RawItem]:
        body = await self._fetch_body()
        parsed = feedparser.parse(body)
        if parsed.bozo and not parsed.entries:
            raise ValueError(f"Feed at {self.feed_url} could not be parsed or was empty")
        items: list[RawItem] = []
        for entry in parsed.entries:
            item = self._to_raw_item(entry)
            if not item.source_item_id:
                # No <guid> and no <link>: we cannot identify or deduplicate it.
                logger.warning(
                    "Skipping entry without id or link in feed %s (source %s)",
                    self.feed_url,
                    self.source_id,
                )
                continue
            items.append(item)
        return items

    async def _fetch_body(self) -> str:
        if self._http_client is not None:
            response = await self._http_client.get(self.feed_url, headers=_HEADERS)
        else:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(self.feed_url, headers=_HEADERS)
        response.raise_for_status()
        return response.text

    def _to_raw_item(self, entry) -> RawItem:
        link = entry.get("link", "")
        return RawItem(
            source_item_id=entry.get("id") or link,
            canonical_url=link,
            original_url=link,
            original_title=entry.get("title", ""),
            original_text=entry.get("summary", ""),
            language=entry.get("language") or self.default_language,
            author=entry.get("author"),
            published_at=_parse_published(entry),
        )


def _parse_published(entry) -> datetime | None:
    parsed = getattr(entry, "published_parsed", None)
    if parsed:
        return datetime(*parsed[:6], tzinfo=timezone.utc)
    return None
