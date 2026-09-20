from pathlib import Path

from src.collectors.sources_config import SourceConfig, load_sources_config

FIXTURE = Path(__file__).parent.parent / "fixtures" / "sources_sample.yaml"
REAL_CONFIG = Path(__file__).parent.parent.parent / "config" / "sources.yaml"


def test_load_sources_config_parses_fixture():
    sources = load_sources_config(FIXTURE)
    assert sources == [
        SourceConfig(
            id="example",
            name="Example Feed",
            type="rss",
            url="https://example.com/feed",
            language="en",
            source_type="press",
            poll_interval_minutes=30,
            active=True,
        )
    ]


def test_real_sources_config_is_valid_and_has_six_active_sources():
    sources = load_sources_config(REAL_CONFIG)
    active_ids = {s.id for s in sources if s.active}
    assert active_ids == {
        "flightglobal",
        "airbus",
        "opex360",
        "bmpd",
        "tass",
        "pprune_military",
    }
