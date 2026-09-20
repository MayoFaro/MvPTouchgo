from pathlib import Path

import httpx
import pytest
import respx

from src.collectors.forum_pprune import PPRuneForumCollector, parse_thread_listing

FIXTURE = (Path(__file__).parent.parent / "fixtures" / "pprune_thread_list.html").read_text()


def test_parse_thread_listing_extracts_all_threads():
    items = parse_thread_listing(FIXTURE, base_url="https://www.pprune.org/military-aviation/")

    assert len(items) == 3
    first = items[0]
    assert first.source_item_id == "654321-new-fighter-programme.html"
    assert first.original_title == "New fighter programme announced"
    assert first.original_url == "https://www.pprune.org/military-aviation/654321-new-fighter-programme.html"
    assert first.language == "en"


@pytest.mark.asyncio
@respx.mock
async def test_fetch_uses_parse_thread_listing():
    respx.get("https://www.pprune.org/military-aviation/").mock(
        return_value=httpx.Response(200, text=FIXTURE)
    )
    collector = PPRuneForumCollector(
        source_id="pprune_military",
        listing_url="https://www.pprune.org/military-aviation/",
    )

    items = await collector.fetch()

    assert len(items) == 3
