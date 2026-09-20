# tests/test_integration_pipeline.py
from pathlib import Path

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from src.api.main import app, get_session
from src.collectors.runner import run_collection
from src.collectors.sources_config import SourceConfig
from src.collectors.factory import build_collector
from src.db.models import NewsItem

FEED = (Path(__file__).parent / "fixtures" / "sample_feed.xml").read_text()


@pytest.mark.asyncio
@respx.mock
async def test_full_pipeline_from_collection_to_api(db_session, make_source):
    make_source(source_id="flightglobal", url="https://example.com/feed")
    config = SourceConfig(
        id="flightglobal",
        name="FlightGlobal",
        type="rss",
        url="https://example.com/feed",
        language="en",
        source_type="press",
        poll_interval_minutes=30,
    )
    respx.get("https://example.com/feed").mock(
        return_value=httpx.Response(200, text=FEED, headers={"content-type": "application/rss+xml"})
    )
    collector = build_collector(config)

    result = await run_collection(db_session, config, collector)

    assert result.ok is True
    assert result.inserted == 2
    assert db_session.query(NewsItem).count() == 2

    app.dependency_overrides[get_session] = lambda: db_session
    try:
        response = TestClient(app).get("/items")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    titles = {item["original_title"] for item in response.json()}
    assert titles == {"First article", "Second article"}
