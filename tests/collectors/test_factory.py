import pytest

from src.collectors.factory import build_collector
from src.collectors.forum_pprune import PPRuneForumCollector
from src.collectors.rss import RSSCollector
from src.collectors.sources_config import SourceConfig


def _config(**overrides) -> SourceConfig:
    base = dict(
        id="s1",
        name="Source 1",
        type="rss",
        url="https://example.com/feed",
        language="en",
        source_type="press",
        poll_interval_minutes=30,
    )
    base.update(overrides)
    return SourceConfig(**base)


def test_build_collector_rss():
    collector = build_collector(_config(type="rss"))
    assert isinstance(collector, RSSCollector)
    assert collector.source_id == "s1"
    assert collector.feed_url == "https://example.com/feed"


def test_build_collector_forum_pprune():
    collector = build_collector(_config(type="forum_pprune"))
    assert isinstance(collector, PPRuneForumCollector)
    assert collector.listing_url == "https://example.com/feed"


def test_build_collector_unknown_type_raises():
    with pytest.raises(ValueError, match="Unknown collector type"):
        build_collector(_config(type="carrier_pigeon"))
