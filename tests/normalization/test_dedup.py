from datetime import datetime, timezone

from src.db.models import NewsItem
from src.normalization.dedup import find_duplicate, jaccard_similarity


def _insert_item(db_session, source_id: str = "flightglobal", **overrides) -> NewsItem:
    defaults = dict(
        source_id=source_id,
        source_item_id=overrides.pop("source_item_id", "seed"),
        canonical_url="https://example.com/seed",
        original_url="https://example.com/seed",
        original_title="Airbus unveils new variant",
        original_text="Body text",
        content_hash="seedhash",
        published_at=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    item = NewsItem(**defaults)
    db_session.add(item)
    db_session.commit()
    return item


def test_jaccard_similarity_identical_strings_is_one():
    assert jaccard_similarity("airbus unveils new variant", "airbus unveils new variant") == 1.0


def test_jaccard_similarity_disjoint_strings_is_zero():
    assert jaccard_similarity("airbus unveils variant", "boeing delivers order") == 0.0


def test_find_duplicate_matches_by_canonical_url(db_session, make_source):
    make_source(source_id="flightglobal")
    seed = _insert_item(db_session)

    match = find_duplicate(
        db_session,
        canonical_url="https://example.com/seed",
        content_hash="different-hash",
        original_title="Unrelated title",
        reference_date=datetime(2030, 1, 1, tzinfo=timezone.utc),
    )

    assert match is not None
    assert match.id == seed.id


def test_find_duplicate_matches_by_content_hash(db_session, make_source):
    make_source(source_id="flightglobal")
    seed = _insert_item(db_session)

    match = find_duplicate(
        db_session,
        canonical_url="https://example.com/different",
        content_hash="seedhash",
        original_title="Unrelated title",
        reference_date=datetime(2030, 1, 1, tzinfo=timezone.utc),
    )

    assert match is not None
    assert match.id == seed.id


def test_find_duplicate_matches_by_similar_title_within_window(db_session, make_source):
    make_source(source_id="flightglobal")
    seed = _insert_item(db_session)

    match = find_duplicate(
        db_session,
        canonical_url="https://example.com/different",
        content_hash="different-hash",
        original_title="Airbus unveils new variant",
        reference_date=datetime(2026, 1, 2, 8, 0, tzinfo=timezone.utc),
    )

    assert match is not None
    assert match.id == seed.id


def test_find_duplicate_ignores_match_outside_date_window(db_session, make_source):
    make_source(source_id="flightglobal")
    _insert_item(db_session)

    match = find_duplicate(
        db_session,
        canonical_url="https://example.com/different",
        content_hash="different-hash",
        original_title="Airbus unveils new variant",
        reference_date=datetime(2026, 1, 10, tzinfo=timezone.utc),
    )

    assert match is None


def test_find_duplicate_ignores_dissimilar_title(db_session, make_source):
    make_source(source_id="flightglobal")
    _insert_item(db_session)

    match = find_duplicate(
        db_session,
        canonical_url="https://example.com/different",
        content_hash="different-hash",
        original_title="Boeing delivers first order",
        reference_date=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
    )

    assert match is None


def test_find_duplicate_returns_none_when_no_items_exist(db_session):
    match = find_duplicate(
        db_session,
        canonical_url="https://example.com/none",
        content_hash="nohash",
        original_title="Anything",
        reference_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    assert match is None
