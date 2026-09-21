import os

from src.config import Settings


def test_settings_read_from_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@host:5432/db")
    monkeypatch.setenv("SOURCES_CONFIG_PATH", "config/sources.yaml")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")
    monkeypatch.setenv("CLASSIFICATION_BATCH_SIZE", "5")
    monkeypatch.setenv("CLASSIFICATION_INTERVAL_MINUTES", "10")
    settings = Settings()
    assert settings.database_url == "postgresql+psycopg://u:p@host:5432/db"
    assert settings.sources_config_path == "config/sources.yaml"
    assert settings.anthropic_api_key == "sk-test-key"
    assert settings.classification_batch_size == 5
    assert settings.classification_interval_minutes == 10


def test_settings_have_defaults(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("SOURCES_CONFIG_PATH", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLASSIFICATION_BATCH_SIZE", raising=False)
    monkeypatch.delenv("CLASSIFICATION_INTERVAL_MINUTES", raising=False)
    settings = Settings(_env_file=None)
    assert "touchgo_news" in settings.database_url
    assert settings.sources_config_path == "config/sources.yaml"
    assert settings.anthropic_api_key == ""
    assert settings.classification_batch_size == 20
    assert settings.classification_interval_minutes == 3
