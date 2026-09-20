from src.collectors.base import Collector
from src.collectors.forum_pprune import PPRuneForumCollector
from src.collectors.rss import RSSCollector
from src.collectors.sources_config import SourceConfig


def build_collector(source_config: SourceConfig) -> Collector:
    if source_config.type == "rss":
        return RSSCollector(source_id=source_config.id, feed_url=source_config.url)
    if source_config.type == "forum_pprune":
        return PPRuneForumCollector(source_id=source_config.id, listing_url=source_config.url)
    raise ValueError(f"Unknown collector type: {source_config.type}")
