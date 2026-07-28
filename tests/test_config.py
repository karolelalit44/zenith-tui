import os
from config.settings import AppSettings
from config.loader import load_config


def test_default_config():
    """Config reads from env vars set by conftest.py."""
    config = AppSettings()
    assert config.active_provider == os.environ["ZENITH_ACTIVE_PROVIDER"]
    assert config.db_path == os.environ["ZENITH_DB_PATH"]
    assert config.max_context_tokens == int(os.environ["ZENITH_MAX_CONTEXT_TOKENS"])


def test_config_validation():
    try:
        AppSettings(active_provider="")
        assert False, "Should have raised"
    except ValueError:
        pass


def test_load_config(temp_dir):
    config = load_config(str(temp_dir))
    assert config is not None
    assert config.active_provider == os.environ["ZENITH_ACTIVE_PROVIDER"]


def test_get_active_provider_config():
    from config.providers import ProviderConfig
    config = AppSettings(
        providers={"openai": ProviderConfig(model="gpt-4o")},
        active_provider="openai",
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
