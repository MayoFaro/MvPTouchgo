from datetime import datetime
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup

from src.collectors.base import Collector, RawItem

# Selectors verified against a live capture of forum.aeronet-fr.org (phpBB) on
# 2026-09-23: topic rows are `dl.row-item`, the title/link is `a.topictitle`,
# and the last-activity timestamp lives at `dd.lastpost time[datetime]`.
TOPIC_ROW_SELECTOR = "dl.row-item"
TITLE_LINK_SELECTOR = "a.topictitle"
LAST_ACTIVITY_SELECTOR = "dd.lastpost time"

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; TouchGoNewsBot/0.1)"}


def _strip_session_id(url: str) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    query.pop("sid", None)
    new_query = urlencode(query, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


class AeronetForumCollector(Collector):
    def __init__(
        self,
        source_id: str,
        listing_url: str,
        http_client: httpx.AsyncClient | None = None,
    ):
        super().__init__(source_id)
        self.listing_url = listing_url
        self._http_client = http_client

    async def fetch(self) -> list[RawItem]:
        html = await self._fetch_html()
        return parse_topic_listing(html, base_url=self.listing_url)

    async def _fetch_html(self) -> str:
        if self._http_client is not None:
            response = await self._http_client.get(self.listing_url, headers=_HEADERS)
        else:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(self.listing_url, headers=_HEADERS)
        response.raise_for_status()
        return response.text


def parse_topic_listing(html: str, base_url: str) -> list[RawItem]:
    soup = BeautifulSoup(html, "html.parser")
    items: list[RawItem] = []
    for row in soup.select(TOPIC_ROW_SELECTOR):
        link = row.select_one(TITLE_LINK_SELECTOR)
        if link is None or not link.get("href"):
            continue
        href = link["href"]
        full_url = href if href.startswith("http") else str(httpx.URL(base_url).join(href))
        canonical_url = _strip_session_id(full_url)
        thread_id = parse_qs(urlparse(canonical_url).query).get("t", [None])[0]
        title = link.get_text(strip=True)

        published_at = None
        time_tag = row.select_one(LAST_ACTIVITY_SELECTOR)
        if time_tag is not None and time_tag.get("datetime"):
            try:
                published_at = datetime.fromisoformat(time_tag["datetime"])
            except ValueError:
                published_at = None

        items.append(
            RawItem(
                source_item_id=thread_id or canonical_url,
                canonical_url=canonical_url,
                original_url=canonical_url,
                original_title=title,
                original_text=title,
                language="fr",
                published_at=published_at,
            )
        )
    return items
