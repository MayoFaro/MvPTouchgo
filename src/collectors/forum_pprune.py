import httpx
from bs4 import BeautifulSoup

from src.collectors.base import Collector, RawItem

# Best-effort selectors for PPRuNe's vBulletin thread listing. pprune.org is
# behind Cloudflare and could not be inspected live while writing this
# collector — verify against the real page before relying on this in
# production (see the plan's "Known risk" note).
THREAD_ROW_SELECTOR = "li.threadbit"
TITLE_LINK_SELECTOR = "a.title"

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; TouchGoNewsBot/0.1)"}


class PPRuneForumCollector(Collector):
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
        return parse_thread_listing(html, base_url=self.listing_url)

    async def _fetch_html(self) -> str:
        if self._http_client is not None:
            response = await self._http_client.get(self.listing_url, headers=_HEADERS)
        else:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(self.listing_url, headers=_HEADERS)
        response.raise_for_status()
        return response.text


def parse_thread_listing(html: str, base_url: str) -> list[RawItem]:
    soup = BeautifulSoup(html, "html.parser")
    items: list[RawItem] = []
    for row in soup.select(THREAD_ROW_SELECTOR):
        link = row.select_one(TITLE_LINK_SELECTOR)
        if link is None or not link.get("href"):
            continue
        href = link["href"]
        url = href if href.startswith("http") else str(httpx.URL(base_url).join(href))
        thread_id = href.rstrip("/").rsplit("/", 1)[-1]
        title = link.get_text(strip=True)
        items.append(
            RawItem(
                source_item_id=thread_id,
                canonical_url=url,
                original_url=url,
                original_title=title,
                original_text=title,
                language="en",
            )
        )
    return items
