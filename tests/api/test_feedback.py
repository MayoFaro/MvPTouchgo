from fastapi.testclient import TestClient

from src.api.main import app, get_session
from src.db.models import NewsFeedback, NewsItem


def _item(db_session, make_source, **overrides) -> NewsItem:
    make_source(source_id=overrides.pop("source_id", "flightglobal"))
    defaults = dict(
        source_id="flightglobal",
        source_item_id=overrides.pop("source_item_id", "1"),
        canonical_url="https://example.com/a",
        original_url="https://example.com/a",
        original_title="Title",
        original_text="Body",
        primary_category="COMMERCIAL",
        priority="A",
    )
    defaults.update(overrides)
    item = NewsItem(**defaults)
    db_session.add(item)
    db_session.commit()
    return item


def test_feedback_endpoint_updates_the_item_and_returns_it(db_session, make_source):
    item = _item(db_session, make_source)

    app.dependency_overrides[get_session] = lambda: db_session
    try:
        client = TestClient(app)
        response = client.post(
            f"/items/{item.id}/feedback",
            json={"decision": "TRES_INTERESSANT", "reviewer_id": "cedric"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["human_decision"] == "TRES_INTERESSANT"
    assert body["reviewer_id"] == "cedric"

    db_session.expire_all()
    stored = db_session.get(NewsItem, item.id)
    assert stored.human_decision == "TRES_INTERESSANT"
    assert db_session.query(NewsFeedback).filter_by(news_item_id=item.id).count() == 1


def test_feedback_endpoint_returns_404_for_an_unknown_item(db_session):
    app.dependency_overrides[get_session] = lambda: db_session
    try:
        client = TestClient(app)
        response = client.post("/items/999999/feedback", json={"decision": "TRES_INTERESSANT"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404


def test_feedback_endpoint_returns_422_for_an_invalid_decision(db_session, make_source):
    item = _item(db_session, make_source)

    app.dependency_overrides[get_session] = lambda: db_session
    try:
        client = TestClient(app)
        response = client.post(f"/items/{item.id}/feedback", json={"decision": "MAYBE"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_feedback_endpoint_returns_422_when_rejecting_without_a_valid_reason(
    db_session, make_source
):
    item = _item(db_session, make_source)

    app.dependency_overrides[get_session] = lambda: db_session
    try:
        client = TestClient(app)
        response = client.post(f"/items/{item.id}/feedback", json={"decision": "REJETER"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
