from datetime import timezone
from pathlib import Path

import httpx
import pytest
import respx

from src.collectors.forum_aeronet import AeronetForumCollector, parse_topic_listing

FIXTURE = (Path(__file__).parent.parent / "fixtures" / "aeronet_topic_list.html").read_text()


def test_parse_topic_listing_extracts_all_topics():
    items = parse_topic_listing(
        FIXTURE, base_url="https://forum.aeronet-fr.org/viewforum.php?f=58"
    )

    assert len(items) == 3
    first = items[0]
    assert first.source_item_id == "3969"
    assert first.original_title == "[Questions à CUJAS] Sélections AF pilote professionnel"
    assert (
        first.original_url
        == "https://forum.aeronet-fr.org/viewtopic.php?t=3969"
    )
    assert first.language == "fr"
    assert first.published_at is not None
    assert first.published_at.astimezone(timezone.utc).isoformat() == "2022-05-30T09:12:50+00:00"


def test_parse_topic_listing_strips_session_id_from_canonical_url():
    items = parse_topic_listing(
        FIXTURE, base_url="https://forum.aeronet-fr.org/viewforum.php?f=58"
    )

    for item in items:
        assert "sid=" not in item.canonical_url


@pytest.mark.asyncio
@respx.mock
async def test_fetch_uses_parse_topic_listing():
    respx.get("https://forum.aeronet-fr.org/viewforum.php?f=58").mock(
        return_value=httpx.Response(200, text=FIXTURE)
    )
    collector = AeronetForumCollector(
        source_id="aeronet_emplois",
        listing_url="https://forum.aeronet-fr.org/viewforum.php?f=58",
    )

    items = await collector.fetch()

    assert len(items) == 3
