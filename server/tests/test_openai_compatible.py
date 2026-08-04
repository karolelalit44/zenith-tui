from server.persistence.provider_config_repo import read_providers, save_provider_config
from server.providers.llm_provider import LLMProvider


def test_openai_compatible_provider_init():
    provider = LLMProvider(
        name="openai_compatible",
        api_key="sk-testkey123",
        base_url="https://api.tokenrouter.com/v1",
        model="moonshotai/kimi-k3-free",
    )
    assert provider.name == "openai_compatible"
    assert provider.model == "moonshotai/kimi-k3-free"
    assert provider.base_url == "https://api.tokenrouter.com/v1"
    assert provider.api_key == "sk-testkey123"
    assert provider._litellm_model == "openai/moonshotai/kimi-k3-free"


def test_tokenrouter_provider_init():
    provider = LLMProvider(
        name="tokenrouter",
        api_key="sk-testkey123",
        base_url="https://api.tokenrouter.com/v1",
        model="moonshotai/kimi-k3-free",
    )
    assert provider.name == "tokenrouter"
    assert provider.model == "moonshotai/kimi-k3-free"
    assert provider.base_url == "https://api.tokenrouter.com/v1"
    assert provider.api_key == "sk-testkey123"
    assert provider._litellm_model == "openai/moonshotai/kimi-k3-free"


def test_custom_provider_init():
    provider = LLMProvider(
        name="custom",
        api_key="sk-testkey123",
        base_url="https://api.tokenrouter.com/v1",
        model="moonshotai/kimi-k3-free",
    )
    assert provider.name == "custom"
    assert provider.model == "moonshotai/kimi-k3-free"
    assert provider.base_url == "https://api.tokenrouter.com/v1"
    assert provider.api_key == "sk-testkey123"
    assert provider._litellm_model == "openai/moonshotai/kimi-k3-free"


def test_openai_compatible_save_config(tmp_path):
    db_file = str(tmp_path / "test_zenith.db")
    from server.persistence.startup import DatabaseStartupService

    DatabaseStartupService(db_file).run()
    save_provider_config(
        provider="openai_compatible",
        api_key="sk-tokenrouter-secret-key",
        model="moonshotai/kimi-k3-free",
        base_url="https://api.tokenrouter.com/v1",
        max_tokens=4096,
        temperature=0.7,
        db_path=db_file,
    )
    providers = read_providers(db_path=db_file)
    assert "openai_compatible" in providers
    cfg = providers["openai_compatible"]
    assert cfg["api_key"] == "sk-tokenrouter-secret-key"
    assert cfg["model"] == "moonshotai/kimi-k3-free"
    assert cfg["base_url"] == "https://api.tokenrouter.com/v1"
