import httpx
from bs4 import BeautifulSoup

from src.collectors.base import Collector, RawItem

# Selectors verified against a live capture of
# bea.aero/enquetes-de-securite/rapports-bea-transport-commercial/ (TYPO3 news
# search widget) on 2026-09-23: entries are `article.search-entry`, and the
# title/link is `h1.search-entry__title a`. There is no structured date field
# on the row, so published_at is left unset (same pattern as the PPRuNe
# collector, which has the same limitation).
ENTRY_SELECTOR = "article.search-entry"
TITLE_LINK_SELECTOR = "h1.search-entry__title a"

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; TouchGoNewsBot/0.1)"}


class BEACollector(Collector):
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
        return parse_search_results(html, base_url=self.listing_url)

    async def _fetch_html(self) -> str:
        if self._http_client is not None:
            response = await self._http_client.get(self.listing_url, headers=_HEADERS)
        else:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(self.listing_url, headers=_HEADERS)
        response.raise_for_status()
        return response.text


def parse_search_results(html: str, base_url: str) -> list[RawItem]:
    soup = BeautifulSoup(html, "html.parser")
    items: list[RawItem] = []
    for entry in soup.select(ENTRY_SELECTOR):
        link = entry.select_one(TITLE_LINK_SELECTOR)
        if link is None or not link.get("href"):
            continue
        href = link["href"]
        url = href if href.startswith("http") else str(httpx.URL(base_url).join(href))
        source_item_id = url.rstrip("/").rsplit("/", 1)[-1]
        title = link.get_text(strip=True)
        items.append(
            RawItem(
                source_item_id=source_item_id,
                canonical_url=url,
                original_url=url,
                original_title=title,
                original_text=title,
                language="fr",
            )
        )
    return items
