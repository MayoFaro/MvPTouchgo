import pytest

from src.collectors.base import Collector, RawItem


def test_raw_item_requires_core_fields():
    item = RawItem(
        source_item_id="1",
        canonical_url="https://example.com/1",
        original_url="https://example.com/1",
        original_title="Title",
        original_text="Text",
        language="en",
    )
    assert item.author is None
    assert item.published_at is None


def test_collector_is_abstract():
    with pytest.raises(TypeError):
        Collector(source_id="x")  # type: ignore[abstract]


@pytest.mark.asyncio
async def test_collector_subclass_must_implement_fetch():
    class Incomplete(Collector):
        pass

    with pytest.raises(TypeError):
        Incomplete(source_id="x")  # type: ignore[abstract]
