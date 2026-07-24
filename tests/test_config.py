from zenith.config.settings import AppSettings
from zenith.config.loader import load_config


def test_default_config():
    config = AppSettings()
    assert config.active_provider == "openai"
    assert config.db_path == "zenith.db"
    assert config.max_context_tokens == 128000
    assert config.tools.max_iterations == 25


def test_config_validation():
    try:
        AppSettings(active_provider="")
        assert False, "Should have raised"
    except ValueError:
        pass


def test_load_config(temp_dir):
    config = load_config(str(temp_dir))
    assert config is not None
    assert config.active_provider == "openai"


def test_get_active_provider_config():
    from zenith.config.providers import ProviderConfig
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
