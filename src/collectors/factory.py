from src.collectors.base import Collector
from src.collectors.bea import BEACollector
from src.collectors.forum_aeronet import AeronetForumCollector
from src.collectors.forum_pprune import PPRuneForumCollector
from src.collectors.rss import RSSCollector
from src.collectors.sources_config import SourceConfig
from src.collectors.wordpress import WordPressApiCollector


def build_collector(source_config: SourceConfig) -> Collector:
    if source_config.type == "rss":
        return RSSCollector(
            source_id=source_config.id,
            feed_url=source_config.url,
            default_language=source_config.language,
        )
    if source_config.type == "forum_pprune":
        return PPRuneForumCollector(source_id=source_config.id, listing_url=source_config.url)
    if source_config.type == "forum_aeronet":
        return AeronetForumCollector(source_id=source_config.id, listing_url=source_config.url)
    if source_config.type == "bea_search":
        return BEACollector(source_id=source_config.id, listing_url=source_config.url)
    if source_config.type == "wordpress_api":
        return WordPressApiCollector(
            source_id=source_config.id,
            api_url=source_config.url,
            default_language=source_config.language,
        )
    raise ValueError(f"Unknown collector type: {source_config.type}")
