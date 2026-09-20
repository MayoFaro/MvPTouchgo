from src.collectors.base import RawItem
from src.db.models import NewsItem, NewsSource
from src.db.repository import save_raw_items, update_source_run_status


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
