import pytest

import src.classification.job as job_module
from src.classification.client import ClassificationError, ClassificationResult
from src.classification.job import classify_pending_items
from src.db.models import NewsItem


def _pending_item(db_session, make_source, source_id: str, **overrides) -> NewsItem:
    make_source(source_id=source_id)
    defaults = dict(
        source_id=source_id,
        source_item_id=overrides.pop("source_item_id", "1"),
        canonical_url="https://example.com/a",
        original_url="https://example.com/a",
        original_title="Airbus unveils new variant",
        original_text="Body text",
    )
    defaults.update(overrides)
    item = NewsItem(**defaults)
    db_session.add(item)
    db_session.commit()
    return item


@pytest.mark.asyncio
async def test_classify_pending_items_returns_zero_when_nothing_pending(db_session):
    result = await classify_pending_items(db_session, batch_size=10)

    assert result.classified == 0
    assert result.failed == 0


@pytest.mark.asyncio
async def test_classify_pending_items_updates_matched_items(db_session, make_source, monkeypatch):
    item = _pending_item(db_session, make_source, source_id="flightglobal")

    async def fake_classify_item(title, text):
        return ClassificationResult(
            primary_category="MILITAIRE",
            secondary_categories=["ACCIDENT_INCIDENT"],
            classification_confidence=0.9,
            reasoning="test reasoning",
        )

    monkeypatch.setattr(job_module, "classify_item", fake_classify_item)

    result = await classify_pending_items(db_session, batch_size=10)

    assert result.classified == 1
    assert result.failed == 0
    stored = db_session.get(NewsItem, item.id)
    assert stored.primary_category == "MILITAIRE"
    assert stored.secondary_categories == ["ACCIDENT_INCIDENT"]
    assert stored.classification_confidence == 0.9
    assert stored.model_reason == "test reasoning"


@pytest.mark.asyncio
async def test_classify_pending_items_skips_already_classified_items(
    db_session, make_source, monkeypatch
):
    _pending_item(db_session, make_source, source_id="flightglobal", primary_category="COMMERCIAL")

    async def fake_classify_item(title, text):
        raise AssertionError("should not be called for an already-classified item")

    monkeypatch.setattr(job_module, "classify_item", fake_classify_item)

    result = await classify_pending_items(db_session, batch_size=10)

    assert result.classified == 0
    assert result.failed == 0


@pytest.mark.asyncio
async def test_classify_pending_items_isolates_a_single_item_failure(
    db_session, make_source, monkeypatch
):
    failing_item = _pending_item(
        db_session,
        make_source,
        source_id="flightglobal",
        original_title="Failing item title",
        original_text="Failing item body",
    )
    ok_item = _pending_item(
        db_session,
        make_source,
        source_id="reuters",
        original_title="OK item title",
        original_text="OK item body",
    )

    async def fake_classify_item(title, text):
        if title == "Failing item title":
            raise ClassificationError("boom")
        return ClassificationResult(
            primary_category="DIVERS",
            secondary_categories=[],
            classification_confidence=0.4,
            reasoning="ok",
        )

    monkeypatch.setattr(job_module, "classify_item", fake_classify_item)

    result = await classify_pending_items(db_session, batch_size=10)

    assert result.classified == 1
    assert result.failed == 1
    assert db_session.get(NewsItem, failing_item.id).primary_category is None
    assert db_session.get(NewsItem, ok_item.id).primary_category == "DIVERS"


@pytest.mark.asyncio
async def test_classify_pending_items_respects_batch_size(db_session, make_source, monkeypatch):
    _pending_item(db_session, make_source, source_id="flightglobal", source_item_id="1")
    _pending_item(db_session, make_source, source_id="flightglobal", source_item_id="2")
    _pending_item(db_session, make_source, source_id="flightglobal", source_item_id="3")

    async def fake_classify_item(title, text):
        return ClassificationResult(
            primary_category="DIVERS",
            secondary_categories=[],
            classification_confidence=0.5,
            reasoning="ok",
        )

    monkeypatch.setattr(job_module, "classify_item", fake_classify_item)

    result = await classify_pending_items(db_session, batch_size=2)

    assert result.classified == 2
    assert result.failed == 0
