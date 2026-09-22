from fastapi.testclient import TestClient

from src.api.main import app, get_session
from src.db.models import NewsItem


def test_review_page_renders_items(db_session, make_source):
    make_source(source_id="flightglobal")
    db_session.add(
        NewsItem(
            source_id="flightglobal",
            source_item_id="1",
            canonical_url="https://example.com/1",
            original_url="https://example.com/1",
            original_title="Airbus unveils new variant",
            original_text="Body",
            primary_category="COMMERCIAL",
            priority="A",
        )
    )
    db_session.commit()

    app.dependency_overrides[get_session] = lambda: db_session
    try:
        response = TestClient(app).get("/")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Airbus unveils new variant" in response.text


def test_review_page_shows_no_results_message_when_empty(db_session):
    app.dependency_overrides[get_session] = lambda: db_session
    try:
        response = TestClient(app).get("/", params={"priority": "A"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Aucun résultat" in response.text


def test_review_page_rejects_an_invalid_priority(db_session):
    app.dependency_overrides[get_session] = lambda: db_session
    try:
        response = TestClient(app).get("/", params={"priority": "Z"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_review_page_treats_empty_string_filters_as_absent(db_session):
    app.dependency_overrides[get_session] = lambda: db_session
    try:
        response = TestClient(app).get(
            "/", params={"priority": "", "category": "", "since": ""}
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200


def test_review_page_shows_an_inline_error_for_an_invalid_filter(db_session):
    app.dependency_overrides[get_session] = lambda: db_session
    try:
        response = TestClient(app).get("/", params={"priority": "NOTAREALPRIORITY"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert "text/html" in response.headers["content-type"]
    assert "invalid priority" in response.text
