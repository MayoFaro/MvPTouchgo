from datetime import datetime, timezone

from src.db.models import NewsItem


def test_insert_and_query_news_item(db_session, make_source):
    make_source(source_id="flightglobal")
    item = NewsItem(
        source_id="flightglobal",
        source_item_id="abc123",
        canonical_url="https://example.com/a",
        original_url="https://example.com/a",
        original_title="Title",
        original_text="Body",
        language="en",
        published_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    db_session.add(item)
    db_session.commit()

    fetched = db_session.query(NewsItem).filter_by(source_item_id="abc123").one()
    assert fetched.status == "NEW"
    assert fetched.primary_category is None
    assert fetched.detected_at is not None


def test_duplicate_source_item_id_rejected(db_session, make_source):
    make_source(source_id="flightglobal")
    db_session.add(
        NewsItem(
            source_id="flightglobal",
            source_item_id="dup",
            canonical_url="https://example.com/a",
            original_url="https://example.com/a",
            original_title="A",
            original_text="A",
        )
    )
    db_session.commit()

    db_session.add(
        NewsItem(
            source_id="flightglobal",
            source_item_id="dup",
            canonical_url="https://example.com/b",
            original_url="https://example.com/b",
            original_title="B",
            original_text="B",
        )
    )
    import pytest
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        db_session.commit()
