from datetime import datetime, timezone

from bs4 import BeautifulSoup
import httpx

from src.collectors.base import Collector, RawItem

_HEADERS = {"User-Agent": "TouchGoNewsBot/0.1 (+https://touch-go.example)"}


class WordPressApiCollector(Collector):
    """Collect posts exposed by a public WordPress REST endpoint."""

    def __init__(
        self,
        source_id: str,
        api_url: str,
        http_client: httpx.AsyncClient | None = None,
        default_language: str = "",
    ):
        super().__init__(source_id)
        self.api_url = api_url
        self._http_client = http_client
        self.default_language = default_language

    async def fetch(self) -> list[RawItem]:
        entries = await self._fetch_entries()
        if not isinstance(entries, list):
            raise ValueError(f"WordPress API at {self.api_url} did not return a post list")
        return [self._to_raw_item(entry) for entry in entries if entry.get("id") and entry.get("link")]

    async def _fetch_entries(self) -> list[dict]:
        if self._http_client is not None:
            response = await self._http_client.get(self.api_url, headers=_HEADERS)
        else:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                response = await client.get(self.api_url, headers=_HEADERS)
        response.raise_for_status()
        return response.json()

    def _to_raw_item(self, entry: dict) -> RawItem:
        content = entry.get("content", {}).get("rendered") or entry.get("excerpt", {}).get("rendered", "")
        return RawItem(
            source_item_id=str(entry["id"]),
            canonical_url=entry["link"],
            original_url=entry["link"],
            original_title=_text(entry.get("title", {}).get("rendered", "")),
            original_text=_text(content),
            language=self.default_language,
            author=None,
            published_at=_parse_datetime(entry.get("date_gmt") or entry.get("date")),
        )


def _text(html: str) -> str:
    return BeautifulSoup(html, "html.parser").get_text(" ", strip=True)


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
