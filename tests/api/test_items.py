from fastapi.testclient import TestClient

from src.api.main import app, get_session
from src.db.repository import save_raw_items
from src.collectors.base import RawItem
from src.db.models import NewsItem


def test_items_returns_persisted_items(db_session, make_source):
    make_source(source_id="flightglobal")
    save_raw_items(
        db_session,
        "flightglobal",
        [
            RawItem(
                source_item_id="1",
                canonical_url="https://example.com/1",
                original_url="https://example.com/1",
                original_title="Title",
                original_text="Body",
                language="en",
            )
        ],
    )
    stored = db_session.query(NewsItem).filter_by(source_item_id="1").one()
    stored.primary_category = "COMMERCIAL"
    stored.secondary_categories = ["EMPLOI"]
    stored.classification_confidence = 0.75
    stored.classification_attempts = 2
    stored.touchgo_interest = 8
    stored.event_importance = 7
    stored.source_confidence = 6
    stored.urgency = 5
    stored.priority = "A"
    db_session.commit()

    app.dependency_overrides[get_session] = lambda: db_session
    try:
        client = TestClient(app)
        response = client.get("/items")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["original_title"] == "Title"
    assert body[0]["status"] == "NEW"
    assert body[0]["primary_category"] == "COMMERCIAL"
    assert body[0]["secondary_categories"] == ["EMPLOI"]
    assert body[0]["classification_confidence"] == 0.75
    assert body[0]["classification_attempts"] == 2
    assert body[0]["touchgo_interest"] == 8
    assert body[0]["event_importance"] == 7
    assert body[0]["source_confidence"] == 6
    assert body[0]["urgency"] == 5
    assert body[0]["priority"] == "A"
    assert body[0]["duplicate_of"] is None
