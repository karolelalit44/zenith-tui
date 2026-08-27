from server.config.constants import DEFAULT_LLM_MAX_TOKENS, DEFAULT_LLM_TEMPERATURE
from server.providers.llm_provider import LLMProvider
from server.storage import StorageHome
from server.storage.provider_config import read_providers, save_provider_config


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


def test_custom_base_url_preserved(tmp_path):
    provider = LLMProvider(
        name="openai_compatible",
        api_key="",
        base_url="http://localhost:11434/v1",
        model="llama3",
    )
    assert provider.base_url == "http://localhost:11434/v1"


def test_openai_compatible_save_config(temp_dir):
    from server.storage import ensure_materialized

    home = StorageHome(temp_dir)
    ensure_materialized(home)
    save_provider_config(
        home,
        provider="openai_compatible",
        api_key="sk-tokenrouter-secret-key",
        model="moonshotai/kimi-k3-free",
        base_url="https://api.tokenrouter.com/v1",
        max_tokens=DEFAULT_LLM_MAX_TOKENS,
        temperature=DEFAULT_LLM_TEMPERATURE,
    )
    providers = read_providers(home)
    assert "openai_compatible" in providers
    cfg = providers["openai_compatible"]
    # The raw key is readable only through the internal read path and is
    # persisted exclusively inside user_profile.json (decision D5).
    assert cfg["api_key"] == "sk-tokenrouter-secret-key"
    assert cfg["model"] == "moonshotai/kimi-k3-free"
    assert cfg["base_url"] == "https://api.tokenrouter.com/v1"

    profile_text = (temp_dir / "user_profile.json").read_text(encoding="utf-8")
    assert "sk-tokenrouter-secret-key" in profile_text
    for catalog in ("providers.json", "models.json"):
        text = (temp_dir / catalog).read_text(encoding="utf-8")
        assert "sk-tokenrouter-secret-key" not in text
