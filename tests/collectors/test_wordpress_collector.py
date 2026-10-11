from datetime import datetime, timezone

import httpx
import pytest
import respx

from src.collectors.wordpress import WordPressApiCollector


@pytest.mark.asyncio
@respx.mock
async def test_wordpress_collector_parses_posts_into_raw_items():
    endpoint = "https://example.com/wp-json/wp/v2/posts"
    respx.get(endpoint).mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": 42,
                    "date_gmt": "2026-10-11T08:30:00",
                    "link": "https://example.com/post",
                    "title": {"rendered": "<em>Defence</em> update"},
                    "excerpt": {"rendered": "<p>Short summary</p>"},
                    "content": {"rendered": "<p>Full <strong>article</strong> text.</p>"},
                }
            ],
        )
    )
    collector = WordPressApiCollector("example", endpoint, default_language="fr")

    items = await collector.fetch()

    assert len(items) == 1
    assert items[0].source_item_id == "42"
    assert items[0].original_title == "Defence update"
    assert items[0].original_text == "Full article text."
    assert items[0].language == "fr"
    assert items[0].published_at == datetime(2026, 10, 11, 8, 30, tzinfo=timezone.utc)


@pytest.mark.asyncio
@respx.mock
async def test_wordpress_collector_rejects_non_list_response():
    endpoint = "https://example.com/wp-json/wp/v2/posts"
    respx.get(endpoint).mock(return_value=httpx.Response(200, json={"code": "rest_forbidden"}))
    collector = WordPressApiCollector("example", endpoint)

    with pytest.raises(ValueError, match="did not return a post list"):
        await collector.fetch()
