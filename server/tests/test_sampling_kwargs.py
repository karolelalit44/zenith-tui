from server.providers.llm_provider import LLMProvider, _get_model_config


def _catalog_with(model_capabilities: dict) -> dict:
    return {
        "providers": {
            "google": {
                "default_model": "gemini-3.5-flash-lite",
                "litellm_prefix": "gemini/",
                "models": [
                    {
                        "id": "gemini-3.5-flash-lite",
                        "name": "Gemini 3.5 Flash-Lite",
                        "context_window": 1048576,
                        "model_capabilities": model_capabilities,
                    }
                ],
            }
        }
    }


def test_default_models_keep_temperature(monkeypatch):
    monkeypatch.setattr(
        "server.providers.llm_provider._get_catalog",
        lambda: _catalog_with({"function_calling": True}),
    )
    provider = LLMProvider(name="openai", model="gpt-4o")
    assert provider.supports_temperature is True
    kwargs = provider._build_completion_kwargs([{"role": "user", "content": "hi"}])
    assert kwargs["temperature"] == provider.temperature


def test_gemini_3_plus_drops_temperature_by_default(monkeypatch):
    monkeypatch.setattr(
        "server.providers.llm_provider._get_catalog",
        lambda: _catalog_with({"function_calling": True}),
    )
    provider = LLMProvider(name="google", model="gemini-3.5-flash-lite")
    assert provider.supports_temperature is False
    kwargs = provider._build_completion_kwargs([{"role": "user", "content": "hi"}])
    assert "temperature" not in kwargs


def test_gemini_3_plus_safety_net_overrides_capability(monkeypatch):
    # Even if the catalog claims temperature support for a Gemini 3.x model,
    # the name-based safety net must still drop temperature regardless of
    # capabilities.
    monkeypatch.setattr(
        "server.providers.llm_provider._get_catalog",
        lambda: _catalog_with(
            {"function_calling": True, "supports_temperature": True}
        ),
    )
    provider = LLMProvider(name="google", model="gemini-3.5-flash-lite")
    assert provider.supports_temperature is True
    kwargs = provider._build_completion_kwargs([{"role": "user", "content": "hi"}])
    assert "temperature" not in kwargs


def test_deprecated_sampling_params_are_filtered_from_extra_params(monkeypatch):
    monkeypatch.setattr(
        "server.providers.llm_provider._get_catalog",
        lambda: _catalog_with({"function_calling": True}),
    )
    provider = LLMProvider(
        name="google",
        model="gemini-3.5-flash-lite",
        extra_params={"top_p": 0.9, "top_k": 40, "frequency_penalty": 0.5},
    )
    kwargs = provider._build_completion_kwargs([{"role": "user", "content": "hi"}])
    assert "temperature" not in kwargs
    assert "top_p" not in kwargs
    assert "top_k" not in kwargs
    assert "frequency_penalty" not in kwargs


def test_model_without_temperature_support_omits_temperature(monkeypatch):
    monkeypatch.setattr(
        "server.providers.llm_provider._get_catalog",
        lambda: _catalog_with({"function_calling": True, "supports_temperature": False}),
    )
    provider = LLMProvider(name="google", model="gemini-3.5-flash-lite")
    assert provider.supports_temperature is False
    kwargs = provider._build_completion_kwargs([{"role": "user", "content": "hi"}])
    assert "temperature" not in kwargs
    assert kwargs["max_tokens"] == provider.max_tokens


def test_capability_controls_streaming_kwargs(monkeypatch):
    monkeypatch.setattr(
        "server.providers.llm_provider._get_catalog",
        lambda: _catalog_with({"function_calling": True}),
    )
    provider = LLMProvider(name="google", model="gemini-3.5-flash-lite")
    provider.supports_temperature = False
    kwargs = provider._build_completion_kwargs(
        [{"role": "user", "content": "hi"}], stream=True, tools=[]
    )
    assert "temperature" not in kwargs
    assert kwargs["stream"] is True


def test_get_model_config_reads_capability(monkeypatch):
    monkeypatch.setattr(
        "server.providers.llm_provider._get_catalog",
        lambda: _catalog_with({"function_calling": True, "supports_temperature": False}),
    )
    cfg = _get_model_config("google", "gemini-3.5-flash-lite")
    assert cfg["supports_temperature"] is False
