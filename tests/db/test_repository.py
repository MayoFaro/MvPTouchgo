from src.collectors.base import RawItem
from src.collectors.sources_config import SourceConfig
from src.db.models import NewsItem, NewsSource
from src.db.repository import save_raw_items, sync_sources, update_source_run_status
from src.normalization.text import compute_content_hash


def _source_config(source_id: str = "flightglobal", **overrides) -> SourceConfig:
    base = dict(
        id=source_id,
        name="FlightGlobal",
        type="rss",
        url="https://example.com/feed",
        language="en",
        source_type="press",
        poll_interval_minutes=30,
        active=True,
    )
    base.update(overrides)
    return SourceConfig(**base)


def _raw_item(source_item_id: str) -> RawItem:
    return RawItem(
        source_item_id=source_item_id,
        canonical_url=f"https://example.com/{source_item_id}",
        original_url=f"https://example.com/{source_item_id}",
        original_title=f"Title {source_item_id}",
        original_text="Body",
        language="en",
    )


def test_save_raw_items_inserts_new_items(db_session, make_source):
    make_source(source_id="flightglobal")

    result = save_raw_items(db_session, "flightglobal", [_raw_item("1"), _raw_item("2")])

    assert result.inserted == 2
    assert result.skipped_duplicates == 0
    assert db_session.query(NewsItem).count() == 2


def test_save_raw_items_skips_existing_duplicates(db_session, make_source):
    make_source(source_id="flightglobal")
    save_raw_items(db_session, "flightglobal", [_raw_item("1")])

    result = save_raw_items(db_session, "flightglobal", [_raw_item("1"), _raw_item("2")])

    assert result.inserted == 1
    assert result.skipped_duplicates == 1
    assert db_session.query(NewsItem).count() == 2


def test_save_raw_items_skips_in_batch_duplicates(db_session, make_source):
    """Two entries sharing a source_item_id in one batch must not abort the commit."""
    make_source(source_id="flightglobal")

    result = save_raw_items(
        db_session, "flightglobal", [_raw_item(""), _raw_item(""), _raw_item("2")]
    )

    assert result.inserted == 2
    assert result.skipped_duplicates == 1
    assert db_session.query(NewsItem).count() == 2


def test_sync_sources_creates_missing_source(db_session):
    sync_sources(db_session, [_source_config("opex360", name="Opex360", language="fr")])

    source = db_session.get(NewsSource, "opex360")
    assert source is not None
    assert source.name == "Opex360"
    assert source.url == "https://example.com/feed"
    assert source.source_type == "press"
    assert source.language == "fr"
    assert source.active is True
    assert source.confirmation_level is None
    assert source.detection_value is None
    assert source.config is None


def test_sync_sources_updates_existing_source(db_session):
    sync_sources(db_session, [_source_config("opex360", name="Opex360", language="fr")])

    sync_sources(
        db_session,
        [
            _source_config(
                "opex360",
                name="Opex360 (renamed)",
                url="https://opex360.example/feed",
                language="en",
                source_type="media",
                active=False,
            )
        ],
    )

    source = db_session.get(NewsSource, "opex360")
    assert source.name == "Opex360 (renamed)"
    assert source.url == "https://opex360.example/feed"
    assert source.language == "en"
    assert source.source_type == "media"
    assert source.active is False
    assert db_session.query(NewsSource).count() == 1


def test_sync_sources_preserves_run_status_columns(db_session, make_source):
    make_source(source_id="flightglobal")
    update_source_run_status(db_session, "flightglobal", status="FAILED", error="timeout")
    before = db_session.get(NewsSource, "flightglobal").last_run_at

    sync_sources(db_session, [_source_config("flightglobal", name="Renamed")])

    source = db_session.get(NewsSource, "flightglobal")
    assert source.name == "Renamed"
    assert source.last_run_status == "FAILED"
    assert source.last_run_error == "timeout"
    assert source.last_run_at == before


def test_update_source_run_status_records_success(db_session, make_source):
    make_source(source_id="flightglobal")

    update_source_run_status(db_session, "flightglobal", status="OK")

    source = db_session.get(NewsSource, "flightglobal")
    assert source.last_run_status == "OK"
    assert source.last_run_at is not None
    assert source.last_run_error is None


def test_update_source_run_status_records_failure(db_session, make_source):
    make_source(source_id="flightglobal")

    update_source_run_status(db_session, "flightglobal", status="FAILED", error="timeout")

    source = db_session.get(NewsSource, "flightglobal")
    assert source.last_run_status == "FAILED"
    assert source.last_run_error == "timeout"


def test_save_raw_items_canonicalizes_the_url(db_session, make_source):
    make_source(source_id="flightglobal")
    item = RawItem(
        source_item_id="1",
        canonical_url="https://example.com/a",
        original_url="https://Example.com/a?utm_source=newsletter",
        original_title="Title",
        original_text="Body",
        language="en",
    )

    save_raw_items(db_session, "flightglobal", [item])

    stored = db_session.query(NewsItem).filter_by(source_item_id="1").one()
    assert stored.canonical_url == "https://example.com/a"


def test_save_raw_items_computes_content_hash(db_session, make_source):
    make_source(source_id="flightglobal")
    item = RawItem(
        source_item_id="1",
        canonical_url="https://example.com/a",
        original_url="https://example.com/a",
        original_title="Some Title",
        original_text="Some body text",
        language="en",
    )

    save_raw_items(db_session, "flightglobal", [item])

    stored = db_session.query(NewsItem).filter_by(source_item_id="1").one()
    assert stored.content_hash == compute_content_hash("Some Title", "Some body text")
