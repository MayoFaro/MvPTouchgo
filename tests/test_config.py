import os

from src.config import Settings


def test_settings_read_from_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@host:5432/db")
    monkeypatch.setenv("SOURCES_CONFIG_PATH", "config/sources.yaml")
    settings = Settings()
    assert settings.database_url == "postgresql+psycopg://u:p@host:5432/db"
    assert settings.sources_config_path == "config/sources.yaml"


def test_settings_have_defaults(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("SOURCES_CONFIG_PATH", raising=False)
    settings = Settings(_env_file=None)
    assert "touchgo_news" in settings.database_url
    assert settings.sources_config_path == "config/sources.yaml"
