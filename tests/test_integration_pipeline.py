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
import src.classification.job as job_module
from src.classification.client import ClassificationResult
from src.classification.job import classify_pending_items
import src.scoring.job as scoring_job_module
from src.scoring.client import ScoringResult
from src.scoring.job import score_pending_items
from src.config import get_settings

FEED = (Path(__file__).parent / "fixtures" / "sample_feed.xml").read_text()

SECOND_SOURCE_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Reuters Feed</title>
    <item>
      <title>First article</title>
      <link>https://reuters.example.com/articles/99</link>
      <guid>https://reuters.example.com/articles/99</guid>
      <description>A different summary confirming the first article.</description>
      <pubDate>Mon, 01 Jan 2026 18:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""


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


@pytest.mark.asyncio
@respx.mock
async def test_cross_source_duplicate_is_linked_but_still_visible(db_session, make_source):
    make_source(source_id="flightglobal", url="https://example.com/feed")
    make_source(source_id="reuters", url="https://reuters.example.com/feed")

    flightglobal_config = SourceConfig(
        id="flightglobal",
        name="FlightGlobal",
        type="rss",
        url="https://example.com/feed",
        language="en",
        source_type="press",
        poll_interval_minutes=30,
    )
    reuters_config = SourceConfig(
        id="reuters",
        name="Reuters",
        type="rss",
        url="https://reuters.example.com/feed",
        language="en",
        source_type="press",
        poll_interval_minutes=30,
    )
    respx.get("https://example.com/feed").mock(
        return_value=httpx.Response(200, text=FEED, headers={"content-type": "application/rss+xml"})
    )
    respx.get("https://reuters.example.com/feed").mock(
        return_value=httpx.Response(
            200, text=SECOND_SOURCE_FEED, headers={"content-type": "application/rss+xml"}
        )
    )

    first_result = await run_collection(
        db_session, flightglobal_config, build_collector(flightglobal_config)
    )
    assert first_result.ok is True
    assert first_result.inserted == 2

    second_result = await run_collection(
        db_session, reuters_config, build_collector(reuters_config)
    )
    assert second_result.ok is True
    assert second_result.inserted == 1

    flightglobal_first_article = (
        db_session.query(NewsItem)
        .filter_by(source_id="flightglobal", original_title="First article")
        .one()
    )
    reuters_item = db_session.query(NewsItem).filter_by(source_id="reuters").one()
    assert reuters_item.duplicate_of == flightglobal_first_article.id
    assert db_session.query(NewsItem).count() == 3

    app.dependency_overrides[get_session] = lambda: db_session
    try:
        response = TestClient(app).get("/items")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    titles = [item["original_title"] for item in response.json()]
    assert titles.count("First article") == 2
    assert "Second article" in titles


@pytest.mark.asyncio
@respx.mock
async def test_collected_items_get_classified_and_are_visible_via_api(
    db_session, make_source, monkeypatch
):
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
    collection_result = await run_collection(db_session, config, collector)
    assert collection_result.inserted == 2

    async def fake_classify_item(title, text, examples="", client=None):
        return ClassificationResult(
            primary_category="COMMERCIAL",
            secondary_categories=[],
            classification_confidence=0.6,
            reasoning="Test classification.",
        )

    monkeypatch.setattr(job_module, "classify_item", fake_classify_item)

    classification_result = await classify_pending_items(db_session, batch_size=10, max_attempts=5)
    assert classification_result.classified == 2
    assert classification_result.failed == 0

    app.dependency_overrides[get_session] = lambda: db_session
    try:
        response = TestClient(app).get("/items")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert all(item["primary_category"] == "COMMERCIAL" for item in body)
    assert all(item["classification_confidence"] == 0.6 for item in body)


@pytest.mark.asyncio
@respx.mock
async def test_collected_items_get_classified_scored_and_are_visible_via_api(
    db_session, make_source, monkeypatch
):
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
    collection_result = await run_collection(db_session, config, collector)
    assert collection_result.inserted == 2

    async def fake_classify_item(title, text, examples="", client=None):
        return ClassificationResult(
            primary_category="COMMERCIAL",
            secondary_categories=[],
            classification_confidence=0.6,
            reasoning="Test classification.",
        )

    monkeypatch.setattr(job_module, "classify_item", fake_classify_item)

    classification_result = await classify_pending_items(db_session, batch_size=10, max_attempts=5)
    assert classification_result.classified == 2
    assert classification_result.failed == 0

    async def fake_score_item(title, text, source_type, examples="", client=None):
        return ScoringResult(
            touchgo_interest=8,
            event_importance=7,
            source_confidence=6,
            urgency=5,
            priority="A",
            reasoning="Test scoring.",
        )

    monkeypatch.setattr(scoring_job_module, "score_item", fake_score_item)

    scoring_result = await score_pending_items(db_session, batch_size=10, max_attempts=5)
    assert scoring_result.scored == 2
    assert scoring_result.failed == 0

    app.dependency_overrides[get_session] = lambda: db_session
    try:
        response = TestClient(app).get("/items")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert all(item["primary_category"] == "COMMERCIAL" for item in body)
    assert all(item["priority"] == "A" for item in body)
    assert all(item["touchgo_interest"] == 8 for item in body)


@pytest.mark.asyncio
@respx.mock
async def test_scored_items_can_receive_feedback_and_be_filtered_via_the_review_endpoints(
    db_session, make_source, monkeypatch
):
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
    collection_result = await run_collection(db_session, config, collector)
    assert collection_result.inserted == 2

    async def fake_classify_item(title, text, examples="", client=None):
        return ClassificationResult(
            primary_category="COMMERCIAL",
            secondary_categories=[],
            classification_confidence=0.6,
            reasoning="Test classification.",
        )

    monkeypatch.setattr(job_module, "classify_item", fake_classify_item)
    classification_result = await classify_pending_items(db_session, batch_size=10, max_attempts=5)
    assert classification_result.classified == 2

    async def fake_score_item(title, text, source_type, examples="", client=None):
        return ScoringResult(
            touchgo_interest=8,
            event_importance=7,
            source_confidence=6,
            urgency=5,
            priority="A",
            reasoning="Test scoring.",
        )

    monkeypatch.setattr(scoring_job_module, "score_item", fake_score_item)
    scoring_result = await score_pending_items(db_session, batch_size=10, max_attempts=5)
    assert scoring_result.scored == 2

    app.dependency_overrides[get_session] = lambda: db_session
    try:
        client = TestClient(app)

        view_response = client.get("/items", params={"view": "a_voir"})
        assert view_response.status_code == 200
        items = view_response.json()
        assert len(items) == 2

        target_id = items[0]["id"]
        feedback_response = client.post(
            f"/items/{target_id}/feedback", json={"decision": "TRES_INTERESSANT"}
        )
        assert feedback_response.status_code == 200
        assert feedback_response.json()["human_decision"] == "TRES_INTERESSANT"
        assert feedback_response.json()["reviewer_id"]

        after_feedback = client.get("/items", params={"view": "a_voir"}).json()
        treated = next(item for item in after_feedback if item["id"] == target_id)
        assert treated["human_decision"] == "TRES_INTERESSANT"

        page_response = client.get("/", params={"view": "a_voir"})
        assert page_response.status_code == 200
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
@respx.mock
async def test_feedback_examples_are_injected_into_the_next_classification_pass(
    db_session, make_source, monkeypatch
):
    monkeypatch.setenv("ADAPTIVE_MIN_EXAMPLES", "1")
    get_settings.cache_clear()
    try:
        make_source(source_id="flightglobal", url="https://example.com/feed")
        make_source(source_id="reuters", url="https://reuters.example.com/feed")
        flightglobal_config = SourceConfig(
            id="flightglobal",
            name="FlightGlobal",
            type="rss",
            url="https://example.com/feed",
            language="en",
            source_type="press",
            poll_interval_minutes=30,
        )
        reuters_config = SourceConfig(
            id="reuters",
            name="Reuters",
            type="rss",
            url="https://reuters.example.com/feed",
            language="en",
            source_type="press",
            poll_interval_minutes=30,
        )
        respx.get("https://example.com/feed").mock(
            return_value=httpx.Response(
                200, text=FEED, headers={"content-type": "application/rss+xml"}
            )
        )
        respx.get("https://reuters.example.com/feed").mock(
            return_value=httpx.Response(
                200, text=SECOND_SOURCE_FEED, headers={"content-type": "application/rss+xml"}
            )
        )

        first_collection = await run_collection(
            db_session, flightglobal_config, build_collector(flightglobal_config)
        )
        assert first_collection.inserted == 2

        async def fake_classify_item(title, text, examples="", client=None):
            return ClassificationResult(
                primary_category="COMMERCIAL",
                secondary_categories=[],
                classification_confidence=0.6,
                reasoning="Test classification.",
            )

        monkeypatch.setattr(job_module, "classify_item", fake_classify_item)
        first_classification = await classify_pending_items(
            db_session, batch_size=10, max_attempts=5
        )
        assert first_classification.classified == 2

        app.dependency_overrides[get_session] = lambda: db_session
        try:
            client = TestClient(app)
            first_item_id = client.get("/items").json()[0]["id"]
            feedback_response = client.post(
                f"/items/{first_item_id}/feedback",
                json={"decision": "REJETER", "reason": "hors_perimetre"},
            )
            assert feedback_response.status_code == 200
        finally:
            app.dependency_overrides.clear()

        second_collection = await run_collection(
            db_session, reuters_config, build_collector(reuters_config)
        )
        assert second_collection.inserted == 1

        received_examples = []

        async def spy_classify_item(title, text, examples="", client=None):
            received_examples.append(examples)
            return ClassificationResult(
                primary_category="DIVERS",
                secondary_categories=[],
                classification_confidence=0.5,
                reasoning="Second pass.",
            )

        monkeypatch.setattr(job_module, "classify_item", spy_classify_item)
        second_classification = await classify_pending_items(
            db_session, batch_size=10, max_attempts=5
        )
        assert second_classification.classified == 1
        assert len(received_examples) == 1
        assert "hors périmètre Touch-Go" in received_examples[0]
    finally:
        get_settings.cache_clear()
