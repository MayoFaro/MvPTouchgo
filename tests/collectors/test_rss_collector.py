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
async def test_rss_collector_uses_default_language_when_feed_has_none():
    respx.get("https://example.com/feed").mock(
        return_value=httpx.Response(200, text=FIXTURE, headers={"content-type": "application/rss+xml"})
    )
    collector = RSSCollector(
        source_id="example", feed_url="https://example.com/feed", default_language="fr"
    )

    items = await collector.fetch()

    assert [item.language for item in items] == ["fr", "fr"]


@pytest.mark.asyncio
@respx.mock
async def test_rss_collector_skips_entries_without_id_or_link():
    feed = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0"><channel><title>Sample</title>
      <item><title>No identity A</title><description>a</description></item>
      <item><title>No identity B</title><description>b</description></item>
      <item><title>Good</title><link>https://example.com/ok</link></item>
    </channel></rss>"""
    respx.get("https://example.com/feed").mock(
        return_value=httpx.Response(200, text=feed, headers={"content-type": "application/rss+xml"})
    )
    collector = RSSCollector(source_id="example", feed_url="https://example.com/feed")

    items = await collector.fetch()

    assert [item.source_item_id for item in items] == ["https://example.com/ok"]


@pytest.mark.asyncio
@respx.mock
async def test_rss_collector_raises_on_malformed_empty_feed():
    respx.get("https://example.com/feed").mock(
        return_value=httpx.Response(200, text="<html>this is not a feed", headers={"content-type": "text/html"})
    )
    collector = RSSCollector(source_id="example", feed_url="https://example.com/feed")

    with pytest.raises(ValueError, match="could not be parsed or was empty"):
        await collector.fetch()


@pytest.mark.asyncio
@respx.mock
async def test_rss_collector_accepts_well_formed_empty_feed():
    feed = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<rss version="2.0"><channel><title>Nothing today</title></channel></rss>'
    )
    respx.get("https://example.com/feed").mock(
        return_value=httpx.Response(200, text=feed, headers={"content-type": "application/rss+xml"})
    )
    collector = RSSCollector(source_id="example", feed_url="https://example.com/feed")

    assert await collector.fetch() == []


@pytest.mark.asyncio
@respx.mock
async def test_rss_collector_raises_on_http_error():
    respx.get("https://example.com/feed").mock(return_value=httpx.Response(500))
    collector = RSSCollector(source_id="example", feed_url="https://example.com/feed")

    with pytest.raises(httpx.HTTPStatusError):
        await collector.fetch()
