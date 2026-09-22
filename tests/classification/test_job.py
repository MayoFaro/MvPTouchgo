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
    result = await classify_pending_items(db_session, batch_size=10, max_attempts=5)

    assert result.classified == 0
    assert result.failed == 0


@pytest.mark.asyncio
async def test_classify_pending_items_updates_matched_items(db_session, make_source, monkeypatch):
    item = _pending_item(db_session, make_source, source_id="flightglobal")

    async def fake_classify_item(title, text, examples="", client=None):
        return ClassificationResult(
            primary_category="MILITAIRE",
            secondary_categories=["ACCIDENT_INCIDENT"],
            classification_confidence=0.9,
            reasoning="test reasoning",
        )

    monkeypatch.setattr(job_module, "classify_item", fake_classify_item)

    result = await classify_pending_items(db_session, batch_size=10, max_attempts=5)

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

    async def fake_classify_item(title, text, examples="", client=None):
        raise AssertionError("should not be called for an already-classified item")

    monkeypatch.setattr(job_module, "classify_item", fake_classify_item)

    result = await classify_pending_items(db_session, batch_size=10, max_attempts=5)

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

    async def fake_classify_item(title, text, examples="", client=None):
        if title == "Failing item title":
            raise ClassificationError("boom")
        return ClassificationResult(
            primary_category="DIVERS",
            secondary_categories=[],
            classification_confidence=0.4,
            reasoning="ok",
        )

    monkeypatch.setattr(job_module, "classify_item", fake_classify_item)

    result = await classify_pending_items(db_session, batch_size=10, max_attempts=5)

    assert result.classified == 1
    assert result.failed == 1
    assert db_session.get(NewsItem, failing_item.id).primary_category is None
    assert db_session.get(NewsItem, ok_item.id).primary_category == "DIVERS"


@pytest.mark.asyncio
async def test_classify_pending_items_isolates_a_non_classification_error(
    db_session, make_source, monkeypatch
):
    """A bug, a DB error, or any other non-ClassificationError failure on one item
    must not abort the rest of the batch, and must not leave the session in a
    broken state for the next iteration's commit."""
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

    async def fake_classify_item(title, text, examples="", client=None):
        if title == "Failing item title":
            raise RuntimeError("unexpected bug")
        return ClassificationResult(
            primary_category="DIVERS",
            secondary_categories=[],
            classification_confidence=0.4,
            reasoning="ok",
        )

    monkeypatch.setattr(job_module, "classify_item", fake_classify_item)

    result = await classify_pending_items(db_session, batch_size=10, max_attempts=5)

    assert result.classified == 1
    assert result.failed == 1
    assert db_session.get(NewsItem, failing_item.id).primary_category is None
    assert db_session.get(NewsItem, ok_item.id).primary_category == "DIVERS"


@pytest.mark.asyncio
async def test_classify_pending_items_respects_batch_size(db_session, make_source, monkeypatch):
    _pending_item(db_session, make_source, source_id="flightglobal-1", source_item_id="1")
    _pending_item(db_session, make_source, source_id="flightglobal-2", source_item_id="2")
    _pending_item(db_session, make_source, source_id="flightglobal-3", source_item_id="3")

    async def fake_classify_item(title, text, examples="", client=None):
        return ClassificationResult(
            primary_category="DIVERS",
            secondary_categories=[],
            classification_confidence=0.5,
            reasoning="ok",
        )

    monkeypatch.setattr(job_module, "classify_item", fake_classify_item)

    result = await classify_pending_items(db_session, batch_size=2, max_attempts=5)

    assert result.classified == 2
    assert result.failed == 0


@pytest.mark.asyncio
async def test_classify_pending_items_excludes_items_that_reached_max_attempts(
    db_session, make_source, monkeypatch
):
    exhausted_item = _pending_item(
        db_session, make_source, source_id="flightglobal", classification_attempts=3
    )

    async def fake_classify_item(title, text, examples="", client=None):
        raise AssertionError("should not be called for an item that reached max_attempts")

    monkeypatch.setattr(job_module, "classify_item", fake_classify_item)

    result = await classify_pending_items(db_session, batch_size=10, max_attempts=3)

    assert result.classified == 0
    assert result.failed == 0
    assert db_session.get(NewsItem, exhausted_item.id).primary_category is None


@pytest.mark.asyncio
async def test_classify_pending_items_increments_attempts_and_logs_reason_on_failure(
    db_session, make_source, monkeypatch
):
    item = _pending_item(db_session, make_source, source_id="flightglobal")

    async def fake_classify_item(title, text, examples="", client=None):
        raise ClassificationError("boom")

    monkeypatch.setattr(job_module, "classify_item", fake_classify_item)

    result = await classify_pending_items(db_session, batch_size=10, max_attempts=5)

    assert result.classified == 0
    assert result.failed == 1
    stored = db_session.get(NewsItem, item.id)
    assert stored.classification_attempts == 1
    errors = stored.model_metadata["classification_errors"]
    assert len(errors) == 1
    assert errors[0]["attempt"] == 1
    assert "boom" in errors[0]["error"]


@pytest.mark.asyncio
async def test_classify_pending_items_survives_a_commit_failure_while_recording_a_failure(
    db_session, make_source, monkeypatch
):
    """Recording the attempts/error-log bookkeeping after a failed item is itself a
    DB write that can fail. It must not escape and abort the rest of the batch —
    the same isolation guarantee the surrounding except block already provides for
    classify_item() failures must hold for this bookkeeping write too."""
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

    async def fake_classify_item(title, text, examples="", client=None):
        if title == "Failing item title":
            raise ClassificationError("boom")
        return ClassificationResult(
            primary_category="DIVERS",
            secondary_categories=[],
            classification_confidence=0.4,
            reasoning="ok",
        )

    monkeypatch.setattr(job_module, "classify_item", fake_classify_item)

    original_commit = db_session.commit
    calls = {"n": 0}

    def flaky_commit():
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("simulated commit failure while recording the error log")
        return original_commit()

    monkeypatch.setattr(db_session, "commit", flaky_commit)

    result = await classify_pending_items(db_session, batch_size=10, max_attempts=5)

    assert result.classified == 1
    assert result.failed == 1
    assert db_session.get(NewsItem, ok_item.id).primary_category == "DIVERS"


@pytest.mark.asyncio
async def test_classify_pending_items_isolates_a_commit_failure_on_the_success_path(
    db_session, make_source, monkeypatch
):
    """The success-path commit (persisting a classified item's fields) is itself a
    DB write that can fail. It must not escape and abort the rest of the batch, and
    the failing item's attempt counter must still be incremented — the same
    isolation guarantee that already applies to classify_item() failures."""
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

    async def fake_classify_item(title, text, examples="", client=None):
        return ClassificationResult(
            primary_category="DIVERS",
            secondary_categories=[],
            classification_confidence=0.4,
            reasoning="ok",
        )

    monkeypatch.setattr(job_module, "classify_item", fake_classify_item)

    original_commit = db_session.commit
    calls = {"n": 0}

    def flaky_commit():
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("simulated commit failure while persisting the classification")
        return original_commit()

    monkeypatch.setattr(db_session, "commit", flaky_commit)

    result = await classify_pending_items(db_session, batch_size=10, max_attempts=5)

    assert result.classified == 1
    assert result.failed == 1
    db_session.expire_all()
    stored_failing = db_session.get(NewsItem, failing_item.id)
    assert stored_failing.primary_category is None
    assert stored_failing.classification_attempts == 1
    assert db_session.get(NewsItem, ok_item.id).primary_category == "DIVERS"


@pytest.mark.asyncio
async def test_classify_pending_items_stops_retrying_once_max_attempts_reached(
    db_session, make_source, monkeypatch
):
    item = _pending_item(db_session, make_source, source_id="flightglobal")

    async def always_fails(title, text, examples="", client=None):
        raise ClassificationError("boom")

    monkeypatch.setattr(job_module, "classify_item", always_fails)

    max_attempts = 3
    for _ in range(max_attempts):
        result = await classify_pending_items(db_session, batch_size=10, max_attempts=max_attempts)
        assert result.classified == 0
        assert result.failed == 1

    # expire_all forces a real re-fetch from the DB rather than reading back
    # the identity-mapped in-memory object (this session has expire_on_commit=False).
    db_session.expire_all()
    stored = db_session.get(NewsItem, item.id)
    assert stored.classification_attempts == max_attempts
    assert len(stored.model_metadata["classification_errors"]) == max_attempts

    async def should_not_be_called(title, text, examples="", client=None):
        raise AssertionError("item exhausted its attempts and must not be retried")

    monkeypatch.setattr(job_module, "classify_item", should_not_be_called)

    result = await classify_pending_items(db_session, batch_size=10, max_attempts=max_attempts)

    assert result.classified == 0
    assert result.failed == 0


@pytest.mark.asyncio
async def test_classify_pending_items_computes_examples_once_per_batch_and_passes_them_through(
    db_session, make_source, monkeypatch
):
    _pending_item(db_session, make_source, source_id="flightglobal", source_item_id="1")
    _pending_item(db_session, make_source, source_id="reuters", source_item_id="2")

    calls = {"build": 0}

    def fake_build_examples(session, min_examples, max_examples):
        calls["build"] += 1
        return "- Item classé COMMERCIAL par le modèle ; retour humain : hors périmètre Touch-Go."

    monkeypatch.setattr(job_module, "build_classification_examples", fake_build_examples)

    received_examples = []

    async def fake_classify_item(title, text, examples="", client=None):
        received_examples.append(examples)
        return ClassificationResult(
            primary_category="COMMERCIAL",
            secondary_categories=[],
            classification_confidence=0.6,
            reasoning="ok",
        )

    monkeypatch.setattr(job_module, "classify_item", fake_classify_item)

    result = await classify_pending_items(db_session, batch_size=10, max_attempts=5)

    assert result.classified == 2
    assert calls["build"] == 1
    assert received_examples == [
        "- Item classé COMMERCIAL par le modèle ; retour humain : hors périmètre Touch-Go.",
        "- Item classé COMMERCIAL par le modèle ; retour humain : hors périmètre Touch-Go.",
    ]


@pytest.mark.asyncio
async def test_classify_pending_items_skips_building_examples_when_nothing_pending(
    db_session, monkeypatch
):
    calls = {"build": 0}

    def fake_build_examples(session, min_examples, max_examples):
        calls["build"] += 1
        return ""

    monkeypatch.setattr(job_module, "build_classification_examples", fake_build_examples)

    result = await classify_pending_items(db_session, batch_size=10, max_attempts=5)

    assert result.classified == 0
    assert calls["build"] == 0


@pytest.mark.asyncio
async def test_classify_pending_items_preserves_existing_model_metadata_keys_on_failure(
    db_session, make_source, monkeypatch
):
    item = _pending_item(
        db_session, make_source, source_id="flightglobal", model_metadata={"foo": "bar"}
    )

    async def fake_classify_item(title, text, examples="", client=None):
        raise ClassificationError("boom")

    monkeypatch.setattr(job_module, "classify_item", fake_classify_item)

    await classify_pending_items(db_session, batch_size=10, max_attempts=5)

    db_session.expire_all()
    stored = db_session.get(NewsItem, item.id)
    assert stored.model_metadata["foo"] == "bar"
    assert len(stored.model_metadata["classification_errors"]) == 1
