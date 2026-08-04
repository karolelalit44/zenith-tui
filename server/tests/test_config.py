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

    config = AppSettings(providers={"openai": ProviderConfig(model="gpt-4o")}, active_provider="openai")
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
