import pytest

import src.scoring.job as job_module
from src.scoring.client import ScoringError, ScoringResult
from src.scoring.job import score_pending_items
from src.db.models import NewsItem


def _scored_pending_item(db_session, make_source, source_id: str, **overrides) -> NewsItem:
    make_source(source_id=source_id, source_type=overrides.pop("source_type", "press"))
    defaults = dict(
        source_id=source_id,
        source_item_id=overrides.pop("source_item_id", "1"),
        canonical_url="https://example.com/a",
        original_url="https://example.com/a",
        original_title="Airbus unveils new variant",
        original_text="Body text",
        primary_category=overrides.pop("primary_category", "COMMERCIAL"),
    )
    defaults.update(overrides)
    item = NewsItem(**defaults)
    db_session.add(item)
    db_session.commit()
    return item


def _valid_result(priority: str = "A") -> ScoringResult:
    return ScoringResult(
        touchgo_interest=8,
        event_importance=7,
        source_confidence=6,
        urgency=5,
        priority=priority,
        reasoning="test reasoning",
    )


@pytest.mark.asyncio
async def test_score_pending_items_returns_zero_when_nothing_pending(db_session):
    result = await score_pending_items(db_session, batch_size=10, max_attempts=5)

    assert result.scored == 0
    assert result.failed == 0


@pytest.mark.asyncio
async def test_score_pending_items_skips_items_not_yet_classified(
    db_session, make_source, monkeypatch
):
    _scored_pending_item(db_session, make_source, source_id="flightglobal", primary_category=None)

    async def fake_score_item(title, text, source_type, client=None):
        raise AssertionError("should not be called for an unclassified item")

    monkeypatch.setattr(job_module, "score_item", fake_score_item)

    result = await score_pending_items(db_session, batch_size=10, max_attempts=5)

    assert result.scored == 0
    assert result.failed == 0


@pytest.mark.asyncio
async def test_score_pending_items_updates_matched_items(db_session, make_source, monkeypatch):
    item = _scored_pending_item(db_session, make_source, source_id="flightglobal")

    async def fake_score_item(title, text, source_type, client=None):
        return _valid_result(priority="A")

    monkeypatch.setattr(job_module, "score_item", fake_score_item)

    result = await score_pending_items(db_session, batch_size=10, max_attempts=5)

    assert result.scored == 1
    assert result.failed == 0
    stored = db_session.get(NewsItem, item.id)
    assert stored.touchgo_interest == 8
    assert stored.event_importance == 7
    assert stored.source_confidence == 6
    assert stored.urgency == 5
    assert stored.priority == "A"
    assert stored.model_metadata["scoring_reasoning"] == "test reasoning"


@pytest.mark.asyncio
async def test_score_pending_items_passes_the_items_source_type(
    db_session, make_source, monkeypatch
):
    _scored_pending_item(db_session, make_source, source_id="pprune", source_type="community")

    received = {}

    async def fake_score_item(title, text, source_type, client=None):
        received["source_type"] = source_type
        return _valid_result()

    monkeypatch.setattr(job_module, "score_item", fake_score_item)

    await score_pending_items(db_session, batch_size=10, max_attempts=5)

    assert received["source_type"] == "community"


@pytest.mark.asyncio
async def test_score_pending_items_skips_already_scored_items(
    db_session, make_source, monkeypatch
):
    _scored_pending_item(db_session, make_source, source_id="flightglobal", touchgo_interest=5)

    async def fake_score_item(title, text, source_type, client=None):
        raise AssertionError("should not be called for an already-scored item")

    monkeypatch.setattr(job_module, "score_item", fake_score_item)

    result = await score_pending_items(db_session, batch_size=10, max_attempts=5)

    assert result.scored == 0
    assert result.failed == 0


@pytest.mark.asyncio
async def test_score_pending_items_isolates_a_single_item_failure(
    db_session, make_source, monkeypatch
):
    failing_item = _scored_pending_item(
        db_session,
        make_source,
        source_id="flightglobal",
        original_title="Failing item title",
        original_text="Failing item body",
    )
    ok_item = _scored_pending_item(
        db_session,
        make_source,
        source_id="reuters",
        original_title="OK item title",
        original_text="OK item body",
    )

    async def fake_score_item(title, text, source_type, client=None):
        if title == "Failing item title":
            raise ScoringError("boom")
        return _valid_result()

    monkeypatch.setattr(job_module, "score_item", fake_score_item)

    result = await score_pending_items(db_session, batch_size=10, max_attempts=5)

    assert result.scored == 1
    assert result.failed == 1
    assert db_session.get(NewsItem, failing_item.id).touchgo_interest is None
    assert db_session.get(NewsItem, ok_item.id).touchgo_interest == 8


@pytest.mark.asyncio
async def test_score_pending_items_isolates_a_non_scoring_error(
    db_session, make_source, monkeypatch
):
    """A bug, a DB error, or any other non-ScoringError failure on one item must
    not abort the rest of the batch, and must not leave the session in a broken
    state for the next iteration's commit."""
    failing_item = _scored_pending_item(
        db_session,
        make_source,
        source_id="flightglobal",
        original_title="Failing item title",
        original_text="Failing item body",
    )
    ok_item = _scored_pending_item(
        db_session,
        make_source,
        source_id="reuters",
        original_title="OK item title",
        original_text="OK item body",
    )

    async def fake_score_item(title, text, source_type, client=None):
        if title == "Failing item title":
            raise RuntimeError("unexpected bug")
        return _valid_result()

    monkeypatch.setattr(job_module, "score_item", fake_score_item)

    result = await score_pending_items(db_session, batch_size=10, max_attempts=5)

    assert result.scored == 1
    assert result.failed == 1
    assert db_session.get(NewsItem, failing_item.id).touchgo_interest is None
    assert db_session.get(NewsItem, ok_item.id).touchgo_interest == 8


@pytest.mark.asyncio
async def test_score_pending_items_respects_batch_size(db_session, make_source, monkeypatch):
    _scored_pending_item(db_session, make_source, source_id="flightglobal-1", source_item_id="1")
    _scored_pending_item(db_session, make_source, source_id="flightglobal-2", source_item_id="2")
    _scored_pending_item(db_session, make_source, source_id="flightglobal-3", source_item_id="3")

    async def fake_score_item(title, text, source_type, client=None):
        return _valid_result()

    monkeypatch.setattr(job_module, "score_item", fake_score_item)

    result = await score_pending_items(db_session, batch_size=2, max_attempts=5)

    assert result.scored == 2
    assert result.failed == 0


@pytest.mark.asyncio
async def test_score_pending_items_excludes_items_that_reached_max_attempts(
    db_session, make_source, monkeypatch
):
    exhausted_item = _scored_pending_item(
        db_session, make_source, source_id="flightglobal", scoring_attempts=3
    )

    async def fake_score_item(title, text, source_type, client=None):
        raise AssertionError("should not be called for an item that reached max_attempts")

    monkeypatch.setattr(job_module, "score_item", fake_score_item)

    result = await score_pending_items(db_session, batch_size=10, max_attempts=3)

    assert result.scored == 0
    assert result.failed == 0
    assert db_session.get(NewsItem, exhausted_item.id).touchgo_interest is None


@pytest.mark.asyncio
async def test_score_pending_items_increments_attempts_and_logs_reason_on_failure(
    db_session, make_source, monkeypatch
):
    item = _scored_pending_item(db_session, make_source, source_id="flightglobal")

    async def fake_score_item(title, text, source_type, client=None):
        raise ScoringError("boom")

    monkeypatch.setattr(job_module, "score_item", fake_score_item)

    result = await score_pending_items(db_session, batch_size=10, max_attempts=5)

    assert result.scored == 0
    assert result.failed == 1
    stored = db_session.get(NewsItem, item.id)
    assert stored.scoring_attempts == 1
    errors = stored.model_metadata["scoring_errors"]
    assert len(errors) == 1
    assert errors[0]["attempt"] == 1
    assert "boom" in errors[0]["error"]


@pytest.mark.asyncio
async def test_score_pending_items_survives_a_commit_failure_while_recording_a_failure(
    db_session, make_source, monkeypatch
):
    """Recording the attempts/error-log bookkeeping after a failed item is itself a
    DB write that can fail. It must not escape and abort the rest of the batch — the
    same isolation guarantee the surrounding except block provides for score_item()
    failures must hold for this bookkeeping write too."""
    failing_item = _scored_pending_item(
        db_session,
        make_source,
        source_id="flightglobal",
        original_title="Failing item title",
        original_text="Failing item body",
    )
    ok_item = _scored_pending_item(
        db_session,
        make_source,
        source_id="reuters",
        original_title="OK item title",
        original_text="OK item body",
    )

    async def fake_score_item(title, text, source_type, client=None):
        if title == "Failing item title":
            raise ScoringError("boom")
        return _valid_result()

    monkeypatch.setattr(job_module, "score_item", fake_score_item)

    original_commit = db_session.commit
    calls = {"n": 0}

    def flaky_commit():
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("simulated commit failure while recording the error log")
        return original_commit()

    monkeypatch.setattr(db_session, "commit", flaky_commit)

    result = await score_pending_items(db_session, batch_size=10, max_attempts=5)

    assert result.scored == 1
    assert result.failed == 1
    assert db_session.get(NewsItem, ok_item.id).touchgo_interest == 8


@pytest.mark.asyncio
async def test_score_pending_items_isolates_a_commit_failure_on_the_success_path(
    db_session, make_source, monkeypatch
):
    """The success-path commit (persisting a scored item's fields) is itself a DB
    write that can fail. It must not escape and abort the rest of the batch, and
    the failing item's attempt counter must still be incremented — the same
    isolation guarantee that already applies to score_item() failures."""
    failing_item = _scored_pending_item(
        db_session,
        make_source,
        source_id="flightglobal",
        original_title="Failing item title",
        original_text="Failing item body",
    )
    ok_item = _scored_pending_item(
        db_session,
        make_source,
        source_id="reuters",
        original_title="OK item title",
        original_text="OK item body",
    )

    async def fake_score_item(title, text, source_type, client=None):
        return _valid_result()

    monkeypatch.setattr(job_module, "score_item", fake_score_item)

    original_commit = db_session.commit
    calls = {"n": 0}

    def flaky_commit():
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("simulated commit failure while persisting the score")
        return original_commit()

    monkeypatch.setattr(db_session, "commit", flaky_commit)

    result = await score_pending_items(db_session, batch_size=10, max_attempts=5)

    assert result.scored == 1
    assert result.failed == 1
    db_session.expire_all()
    stored_failing = db_session.get(NewsItem, failing_item.id)
    assert stored_failing.touchgo_interest is None
    assert stored_failing.scoring_attempts == 1
    assert db_session.get(NewsItem, ok_item.id).touchgo_interest == 8


@pytest.mark.asyncio
async def test_score_pending_items_stops_retrying_once_max_attempts_reached(
    db_session, make_source, monkeypatch
):
    item = _scored_pending_item(db_session, make_source, source_id="flightglobal")

    async def always_fails(title, text, source_type, client=None):
        raise ScoringError("boom")

    monkeypatch.setattr(job_module, "score_item", always_fails)

    max_attempts = 3
    for _ in range(max_attempts):
        result = await score_pending_items(db_session, batch_size=10, max_attempts=max_attempts)
        assert result.scored == 0
        assert result.failed == 1

    # expire_all forces a real re-fetch from the DB rather than reading back
    # the identity-mapped in-memory object (this session has expire_on_commit=False).
    db_session.expire_all()
    stored = db_session.get(NewsItem, item.id)
    assert stored.scoring_attempts == max_attempts
    assert len(stored.model_metadata["scoring_errors"]) == max_attempts

    async def should_not_be_called(title, text, source_type, client=None):
        raise AssertionError("item exhausted its attempts and must not be retried")

    monkeypatch.setattr(job_module, "score_item", should_not_be_called)

    result = await score_pending_items(db_session, batch_size=10, max_attempts=max_attempts)

    assert result.scored == 0
    assert result.failed == 0


@pytest.mark.asyncio
async def test_score_pending_items_preserves_classification_errors_in_model_metadata(
    db_session, make_source, monkeypatch
):
    """model_metadata already holds classification_errors (Sprint 3) on some items.
    Writing scoring_errors must never clobber that pre-existing key."""
    item = _scored_pending_item(
        db_session,
        make_source,
        source_id="flightglobal",
        model_metadata={"classification_errors": [{"attempt": 1, "error": "prior failure"}]},
    )

    async def fake_score_item(title, text, source_type, client=None):
        raise ScoringError("boom")

    monkeypatch.setattr(job_module, "score_item", fake_score_item)

    await score_pending_items(db_session, batch_size=10, max_attempts=5)

    db_session.expire_all()
    stored = db_session.get(NewsItem, item.id)
    assert stored.model_metadata["classification_errors"] == [
        {"attempt": 1, "error": "prior failure"}
    ]
    assert len(stored.model_metadata["scoring_errors"]) == 1
