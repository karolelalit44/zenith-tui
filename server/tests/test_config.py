import os

from server.config.loader import load_config
from server.config.settings import AppSettings


def test_default_config():
    config = AppSettings()
    assert config.active_provider == ""
    assert config.db_path == os.environ["ZENITH_DB_PATH"]
    assert config.max_context_tokens == int(os.environ["ZENITH_MAX_CONTEXT_TOKENS"])


def test_config_validation():
    config = AppSettings(active_provider="")
    assert config.active_provider == ""


def test_load_config(temp_dir):
    config = load_config(str(temp_dir))
    assert config is not None
    assert config.active_provider == ""


def test_get_active_provider_config():
    from server.config.providers import ProviderConfig

    config = AppSettings(
        providers={"openai": ProviderConfig(model="gpt-4o")}, active_provider="openai"
    )
    pc = config.get_active_provider_config()
    assert pc is not None
    assert pc.model == "gpt-4o"


def test_require_active_provider_config_missing():
    config = AppSettings()
    try:
        config.require_active_provider_config()
        assert False, "Should have raised"
    except ValueError as e:
        assert "not configured" in str(e)


def test_context_compaction_threshold_default():
    """New budget setting defaults to the import-time ZENITH_* default when unset."""
    config = AppSettings()
    assert 0.0 <= config.context_compaction_threshold <= 1.0


def test_load_config_context_compaction_threshold_env_override(monkeypatch, temp_dir):
    """A new ZENITH_* scalar env var is honored by load_config() at load time (task 0.3)."""
    monkeypatch.setenv("ZENITH_CONTEXT_COMPACTION_THRESHOLD", "0.62")
    config = load_config(str(temp_dir))
    assert abs(config.context_compaction_threshold - 0.62) < 1e-9


def test_load_config_context_compaction_threshold_invalid_ignored(monkeypatch, temp_dir):
    monkeypatch.setenv("ZENITH_CONTEXT_COMPACTION_THRESHOLD", "not-a-number")
    config = load_config(str(temp_dir))
    assert 0.0 <= config.context_compaction_threshold <= 1.0
