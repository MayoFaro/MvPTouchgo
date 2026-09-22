import pytest

from src.config import get_settings
from src.db.models import NewsFeedback, NewsItem
from src.review.schemas import FeedbackIn
from src.review.service import ItemNotFoundError, submit_feedback


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


def test_submit_feedback_raises_when_item_does_not_exist(db_session):
    with pytest.raises(ItemNotFoundError):
        submit_feedback(db_session, 999999, FeedbackIn(decision="INTERESSANT"))


def test_submit_feedback_updates_the_item_for_a_simple_decision(db_session, make_source):
    item = _item(db_session, make_source)

    updated = submit_feedback(
        db_session, item.id, FeedbackIn(decision="INTERESSANT", reviewer_id="cedric")
    )

    assert updated.human_decision == "INTERESSANT"
    assert updated.human_reason is None
    assert updated.human_comment is None
    assert updated.reviewer_id == "cedric"
    assert updated.reviewed_at is not None


def test_submit_feedback_uses_the_default_reviewer_id_when_none_given(
    db_session, make_source, monkeypatch
):
    monkeypatch.setenv("DEFAULT_REVIEWER_ID", "cedric-default")
    get_settings.cache_clear()
    try:
        item = _item(db_session, make_source)

        updated = submit_feedback(db_session, item.id, FeedbackIn(decision="A_SUIVRE"))

        assert updated.reviewer_id == "cedric-default"
    finally:
        get_settings.cache_clear()


def test_submit_feedback_stores_the_reason_only_when_rejecting(db_session, make_source):
    item = _item(db_session, make_source)

    updated = submit_feedback(
        db_session, item.id, FeedbackIn(decision="REJETER", reason="doublon")
    )

    assert updated.human_reason == "doublon"


def test_submit_feedback_stores_the_comment_when_suggesting_a_new_category(
    db_session, make_source
):
    item = _item(db_session, make_source)

    updated = submit_feedback(
        db_session,
        item.id,
        FeedbackIn(decision="NOUVELLE_CATEGORIE", comment="Catégorie drones civils"),
    )

    assert updated.human_comment == "Catégorie drones civils"


def test_submit_feedback_inserts_a_feedback_history_row(db_session, make_source):
    item = _item(db_session, make_source, primary_category="MILITAIRE", priority="B")

    submit_feedback(db_session, item.id, FeedbackIn(decision="TRES_INTERESSANT", reviewer_id="c"))

    rows = db_session.query(NewsFeedback).filter_by(news_item_id=item.id).all()
    assert len(rows) == 1
    assert rows[0].decision == "TRES_INTERESSANT"
    assert rows[0].previous_priority == "B"
    assert rows[0].previous_category == "MILITAIRE"
    assert rows[0].reviewer_id == "c"


def test_submit_feedback_appends_a_new_history_row_without_deleting_previous_ones(
    db_session, make_source
):
    item = _item(db_session, make_source)

    submit_feedback(db_session, item.id, FeedbackIn(decision="INTERESSANT", reviewer_id="c"))
    submit_feedback(
        db_session,
        item.id,
        FeedbackIn(decision="REJETER", reason="doublon", reviewer_id="c"),
    )

    rows = (
        db_session.query(NewsFeedback)
        .filter_by(news_item_id=item.id)
        .order_by(NewsFeedback.id)
        .all()
    )
    assert len(rows) == 2
    assert rows[0].decision == "INTERESSANT"
    assert rows[1].decision == "REJETER"
    assert item.human_decision == "REJETER"
