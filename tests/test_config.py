import pytest

from config import ConfigurationError, Settings


def test_configuration_rejects_non_numeric_smtp_port(monkeypatch, tmp_path):
    monkeypatch.setenv("SMTP_PORT", "not-a-port")
    with pytest.raises(ConfigurationError, match="must be integers"):
        Settings.from_env(tmp_path)


def test_configuration_rejects_invalid_boolean(monkeypatch, tmp_path):
    monkeypatch.setenv("SMTP_USE_SSL", "sometimes")
    with pytest.raises(ConfigurationError, match="must be true or false"):
        Settings.from_env(tmp_path)


def test_relative_paths_resolve_from_project_directory(monkeypatch, tmp_path):
    monkeypatch.setenv("REPORT_DATABASE_PATH", "custom/data.sqlite")
    settings = Settings.from_env(tmp_path)
    assert settings.database_path == (tmp_path / "custom" / "data.sqlite").resolve()
