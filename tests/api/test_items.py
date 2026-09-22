from datetime import datetime, timedelta, timezone

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
    stored.verification_status = "UNVERIFIED"
    stored.human_decision = "TRES_INTERESSANT"
    stored.human_reason = None
    stored.human_comment = "Bon signal"
    stored.reviewer_id = "cedric"
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
    assert body[0]["verification_status"] == "UNVERIFIED"
    assert body[0]["human_decision"] == "TRES_INTERESSANT"
    assert body[0]["human_reason"] is None
    assert body[0]["human_comment"] == "Bon signal"
    assert body[0]["reviewer_id"] == "cedric"
    assert body[0]["reviewed_at"] is None
    assert body[0]["duplicate_of"] is None


def test_items_filters_by_priority(db_session, make_source):
    make_source(source_id="flightglobal")
    for i, priority in enumerate(["A", "B", "C"]):
        db_session.add(
            NewsItem(
                source_id="flightglobal",
                source_item_id=str(i),
                canonical_url=f"https://example.com/{i}",
                original_url=f"https://example.com/{i}",
                original_title=f"Title {i}",
                original_text="Body",
                priority=priority,
            )
        )
    db_session.commit()

    app.dependency_overrides[get_session] = lambda: db_session
    try:
        response = TestClient(app).get("/items", params={"priority": "B"})
    finally:
        app.dependency_overrides.clear()

    body = response.json()
    assert len(body) == 1
    assert body[0]["priority"] == "B"


def test_items_filters_by_category(db_session, make_source):
    make_source(source_id="flightglobal")
    for i, category in enumerate(["COMMERCIAL", "MILITAIRE"]):
        db_session.add(
            NewsItem(
                source_id="flightglobal",
                source_item_id=str(i),
                canonical_url=f"https://example.com/{i}",
                original_url=f"https://example.com/{i}",
                original_title=f"Title {i}",
                original_text="Body",
                primary_category=category,
            )
        )
    db_session.commit()

    app.dependency_overrides[get_session] = lambda: db_session
    try:
        response = TestClient(app).get("/items", params={"category": "MILITAIRE"})
    finally:
        app.dependency_overrides.clear()

    body = response.json()
    assert len(body) == 1
    assert body[0]["primary_category"] == "MILITAIRE"


def test_items_filters_by_since(db_session, make_source):
    make_source(source_id="flightglobal")
    db_session.add(
        NewsItem(
            source_id="flightglobal",
            source_item_id="old",
            canonical_url="https://example.com/old",
            original_url="https://example.com/old",
            original_title="Old",
            original_text="Body",
            detected_at=datetime.now(timezone.utc) - timedelta(days=10),
        )
    )
    db_session.add(
        NewsItem(
            source_id="flightglobal",
            source_item_id="recent",
            canonical_url="https://example.com/recent",
            original_url="https://example.com/recent",
            original_title="Recent",
            original_text="Body",
            detected_at=datetime.now(timezone.utc),
        )
    )
    db_session.commit()

    app.dependency_overrides[get_session] = lambda: db_session
    try:
        response = TestClient(app).get("/items", params={"since": "24h"})
    finally:
        app.dependency_overrides.clear()

    body = response.json()
    assert len(body) == 1
    assert body[0]["original_title"] == "Recent"


def test_items_view_maps_to_the_corresponding_priority(db_session, make_source):
    make_source(source_id="flightglobal")
    for i, priority in enumerate(["A", "B", "C"]):
        db_session.add(
            NewsItem(
                source_id="flightglobal",
                source_item_id=str(i),
                canonical_url=f"https://example.com/{i}",
                original_url=f"https://example.com/{i}",
                original_title=f"Title {i}",
                original_text="Body",
                priority=priority,
            )
        )
    db_session.commit()

    app.dependency_overrides[get_session] = lambda: db_session
    try:
        response = TestClient(app).get("/items", params={"view": "faible_priorite"})
    finally:
        app.dependency_overrides.clear()

    body = response.json()
    assert len(body) == 1
    assert body[0]["priority"] == "C"


def test_items_explicit_priority_overrides_the_view(db_session, make_source):
    make_source(source_id="flightglobal")
    for i, priority in enumerate(["A", "B"]):
        db_session.add(
            NewsItem(
                source_id="flightglobal",
                source_item_id=str(i),
                canonical_url=f"https://example.com/{i}",
                original_url=f"https://example.com/{i}",
                original_title=f"Title {i}",
                original_text="Body",
                priority=priority,
            )
        )
    db_session.commit()

    app.dependency_overrides[get_session] = lambda: db_session
    try:
        # view says "a_voir" (priority A); explicit priority=B must win.
        response = TestClient(app).get("/items", params={"view": "a_voir", "priority": "B"})
    finally:
        app.dependency_overrides.clear()

    body = response.json()
    assert len(body) == 1
    assert body[0]["priority"] == "B"


def test_items_rejects_an_invalid_priority(db_session):
    app.dependency_overrides[get_session] = lambda: db_session
    try:
        response = TestClient(app).get("/items", params={"priority": "Z"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_items_rejects_an_invalid_category(db_session):
    app.dependency_overrides[get_session] = lambda: db_session
    try:
        response = TestClient(app).get("/items", params={"category": "NOT_A_CATEGORY"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_items_rejects_an_invalid_since(db_session):
    app.dependency_overrides[get_session] = lambda: db_session
    try:
        response = TestClient(app).get("/items", params={"since": "1h"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_items_rejects_an_invalid_view(db_session):
    app.dependency_overrides[get_session] = lambda: db_session
    try:
        response = TestClient(app).get("/items", params={"view": "bogus"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_items_with_null_priority_are_excluded_from_every_view(db_session, make_source):
    make_source(source_id="flightglobal")
    db_session.add(
        NewsItem(
            source_id="flightglobal",
            source_item_id="1",
            canonical_url="https://example.com/1",
            original_url="https://example.com/1",
            original_title="Not scored yet",
            original_text="Body",
        )
    )
    db_session.commit()

    app.dependency_overrides[get_session] = lambda: db_session
    try:
        response = TestClient(app).get("/items", params={"view": "a_voir"})
    finally:
        app.dependency_overrides.clear()

    assert response.json() == []
