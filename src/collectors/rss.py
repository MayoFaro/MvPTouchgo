from datetime import datetime, timezone

import feedparser
import httpx

from src.collectors.base import Collector, RawItem

_HEADERS = {"User-Agent": "TouchGoNewsBot/0.1 (+https://touch-go.example)"}


class RSSCollector(Collector):
    def __init__(
        self,
        source_id: str,
        feed_url: str,
        http_client: httpx.AsyncClient | None = None,
    ):
        super().__init__(source_id)
        self.feed_url = feed_url
        self._http_client = http_client

    async def fetch(self) -> list[RawItem]:
        body = await self._fetch_body()
        parsed = feedparser.parse(body)
        return [self._to_raw_item(entry) for entry in parsed.entries]

    async def _fetch_body(self) -> str:
        if self._http_client is not None:
            response = await self._http_client.get(self.feed_url, headers=_HEADERS)
        else:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(self.feed_url, headers=_HEADERS)
        response.raise_for_status()
        return response.text

    @staticmethod
    def _to_raw_item(entry) -> RawItem:
        link = entry.get("link", "")
        return RawItem(
            source_item_id=entry.get("id") or link,
            canonical_url=link,
            original_url=link,
            original_title=entry.get("title", ""),
            original_text=entry.get("summary", ""),
            language="",
            author=entry.get("author"),
            published_at=_parse_published(entry),
        )


def _parse_published(entry) -> datetime | None:
    parsed = getattr(entry, "published_parsed", None)
    if parsed:
        return datetime(*parsed[:6], tzinfo=timezone.utc)
    return None
