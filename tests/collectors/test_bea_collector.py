from pathlib import Path

import httpx
import pytest
import respx

from src.collectors.bea import BEACollector, parse_search_results

FIXTURE = (Path(__file__).parent.parent / "fixtures" / "bea_search_results.html").read_text()

LISTING_URL = "https://bea.aero/enquetes-de-securite/rapports-bea-transport-commercial/"


def test_parse_search_results_extracts_all_entries():
    items = parse_search_results(FIXTURE, base_url=LISTING_URL)

    assert len(items) == 3
    first = items[0]
    assert (
        first.source_item_id
        == "accident-survenu-au-piper-pa28-immatricule-f-gfie-le-21-12-2024-a-emerainville-77"
    )
    assert first.original_title == "Accident du Piper PA-28 immatriculé F-GFIE le 21/12/2024 à Emerainville (77)"
    assert (
        first.original_url
        == "https://bea.aero/les-enquetes/evenements-notifies/detail/"
        "accident-survenu-au-piper-pa28-immatricule-f-gfie-le-21-12-2024-a-emerainville-77/"
    )
    assert first.language == "fr"


@pytest.mark.asyncio
@respx.mock
async def test_fetch_uses_parse_search_results():
    respx.get(LISTING_URL).mock(return_value=httpx.Response(200, text=FIXTURE))
    collector = BEACollector(source_id="bea_transport_commercial", listing_url=LISTING_URL)

    items = await collector.fetch()

    assert len(items) == 3
