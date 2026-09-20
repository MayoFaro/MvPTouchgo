from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
import respx

from src.collectors.rss import RSSCollector

FIXTURE = (Path(__file__).parent.parent / "fixtures" / "sample_feed.xml").read_text()


@pytest.mark.asyncio
@respx.mock
async def test_rss_collector_parses_entries_into_raw_items():
    respx.get("https://example.com/feed").mock(
        return_value=httpx.Response(200, text=FIXTURE, headers={"content-type": "application/rss+xml"})
    )
    collector = RSSCollector(source_id="example", feed_url="https://example.com/feed")

    items = await collector.fetch()

    assert len(items) == 2
    first = items[0]
    assert first.source_item_id == "https://example.com/articles/1"
    assert first.original_title == "First article"
    assert first.original_url == "https://example.com/articles/1"
    assert first.canonical_url == "https://example.com/articles/1"
    assert first.original_text == "Summary of the first article."
    assert first.author == "jane@example.com"
    assert first.published_at == datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
@respx.mock
async def test_rss_collector_raises_on_http_error():
    respx.get("https://example.com/feed").mock(return_value=httpx.Response(500))
    collector = RSSCollector(source_id="example", feed_url="https://example.com/feed")

    with pytest.raises(httpx.HTTPStatusError):
        await collector.fetch()
