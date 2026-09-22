import os

from src.config import Settings


def test_settings_read_from_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@host:5432/db")
    monkeypatch.setenv("SOURCES_CONFIG_PATH", "config/sources.yaml")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")
    monkeypatch.setenv("CLASSIFICATION_BATCH_SIZE", "5")
    monkeypatch.setenv("CLASSIFICATION_INTERVAL_MINUTES", "10")
    monkeypatch.setenv("CLASSIFICATION_MAX_ATTEMPTS", "3")
    monkeypatch.setenv("SCORING_BATCH_SIZE", "8")
    monkeypatch.setenv("SCORING_INTERVAL_MINUTES", "15")
    monkeypatch.setenv("SCORING_MAX_ATTEMPTS", "4")
    monkeypatch.setenv("DEFAULT_REVIEWER_ID", "cedric")
    monkeypatch.setenv("ADAPTIVE_MIN_EXAMPLES", "2")
    monkeypatch.setenv("ADAPTIVE_MAX_EXAMPLES", "10")
    settings = Settings()
    assert settings.database_url == "postgresql+psycopg://u:p@host:5432/db"
    assert settings.sources_config_path == "config/sources.yaml"
    assert settings.anthropic_api_key == "sk-test-key"
    assert settings.classification_batch_size == 5
    assert settings.classification_interval_minutes == 10
    assert settings.classification_max_attempts == 3
    assert settings.scoring_batch_size == 8
    assert settings.scoring_interval_minutes == 15
    assert settings.scoring_max_attempts == 4
    assert settings.default_reviewer_id == "cedric"
    assert settings.adaptive_min_examples == 2
    assert settings.adaptive_max_examples == 10


def test_settings_have_defaults(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("SOURCES_CONFIG_PATH", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLASSIFICATION_BATCH_SIZE", raising=False)
    monkeypatch.delenv("CLASSIFICATION_INTERVAL_MINUTES", raising=False)
    monkeypatch.delenv("CLASSIFICATION_MAX_ATTEMPTS", raising=False)
    monkeypatch.delenv("SCORING_BATCH_SIZE", raising=False)
    monkeypatch.delenv("SCORING_INTERVAL_MINUTES", raising=False)
    monkeypatch.delenv("SCORING_MAX_ATTEMPTS", raising=False)
    monkeypatch.delenv("DEFAULT_REVIEWER_ID", raising=False)
    monkeypatch.delenv("ADAPTIVE_MIN_EXAMPLES", raising=False)
    monkeypatch.delenv("ADAPTIVE_MAX_EXAMPLES", raising=False)
    settings = Settings(_env_file=None)
    assert "touchgo_news" in settings.database_url
    assert settings.sources_config_path == "config/sources.yaml"
    assert settings.anthropic_api_key == ""
    assert settings.classification_batch_size == 20
    assert settings.classification_interval_minutes == 3
    assert settings.classification_max_attempts == 5
    assert settings.scoring_batch_size == 20
    assert settings.scoring_interval_minutes == 3
    assert settings.scoring_max_attempts == 5
    assert settings.default_reviewer_id == "reviewer"
    assert settings.adaptive_min_examples == 5
    assert settings.adaptive_max_examples == 5
