from server.api.provider_validation import (
    get_provider_catalog,
    get_provider_list,
    get_provider_models,
    set_provider_model,
)
from server.api.schemas import ProviderModelRequest
from server.config.constants import DEFAULT_LLM_MAX_TOKENS, DEFAULT_LLM_TEMPERATURE
from server.providers.validation import STEP_LABELS, validate_provider, validate_provider_collect
from server.storage import StorageHome, ensure_materialized
from server.storage.catalog_compat import load_catalog
from server.storage.profile_store import mask_api_key
from server.storage.provider_config import read_provider_config_full, save_provider_config

GROQ_URL = "https://api.groq.com/openai/v1"


def _home(tmp_path) -> StorageHome:
    h = StorageHome(tmp_path)
    ensure_materialized(h)
    return h


def test_mask_api_key():
    assert mask_api_key(None) == ""
    assert mask_api_key("") == ""
    assert mask_api_key("abcdefgh") == "***efgh"
    # Last-4-only masking: no leading secret material is ever echoed.
    assert mask_api_key("sk-or-v1-1234abcd5678efgh") == "***efgh"
    assert "1234abcd" not in mask_api_key("sk-or-v1-1234abcd5678efgh")
    assert "sk-or-v1" not in mask_api_key("sk-or-v1-1234abcd5678efgh")


def test_read_provider_config_full_masks_key(tmp_path):
    home = _home(tmp_path)
    save_provider_config(
        home,
        provider="groq",
        api_key="gsk-supersecretkey-xyz",
        model="llama-3.3-70b-versatile",
        base_url=GROQ_URL,
        max_tokens=DEFAULT_LLM_MAX_TOKENS,
        temperature=DEFAULT_LLM_TEMPERATURE,
    )
    active, providers = read_provider_config_full(home)
    assert active == "groq"
    p = providers["groq"]
    assert p["api_key_masked"] == "***-xyz"
    assert "gsk-supe" not in p["api_key_masked"]
    assert p["has_api_key"] is True
    assert p["api_key"] == p["api_key_masked"]
    assert "gsk-supersecretkey-xyz" not in p["api_key"]


def test_first_class_roster(tmp_path):
    result = get_provider_list(_home(tmp_path))
    ids = [p.id for p in result.all]
    # Decision D3: exactly four first-class providers.
    assert sorted(ids) == ["gemini", "groq", "openai_compatible", "openrouter"]
    assert result.connected == []
    groq = next(p for p in result.all if p.id == "groq")
    assert groq.validation_status == "unconfigured"
    assert groq.has_api_key is False
    assert groq.models
    assert next(p for p in result.all if p.id == "openai_compatible").custom_flow is True
    gemini = next(p for p in result.all if p.id == "gemini")
    assert gemini.supports_prompt_caching is True
    assert gemini.env_keys  # apiKeyEnv carried through the compat catalog


def test_get_provider_catalog_returns_only_metadata(tmp_path):
    items = get_provider_catalog(_home(tmp_path))
    ids = [i.id for i in items]
    assert "gemini" in ids
    assert "openrouter" in ids
    assert "openai_compatible" in ids
    for item in items:
        assert not hasattr(item, "models")
        assert item.type in ("default", "custom")
    assert next(i for i in items if i.id == "openai_compatible").type == "custom"
    assert next(i for i in items if i.id == "openrouter").type == "default"


def test_get_provider_models_paginated_and_complete(tmp_path):
    home = _home(tmp_path)
    res = get_provider_models("groq", offset=0, limit=2, home=home)
    assert res.total >= 2
    assert len(res.models) == min(2, res.total)
    assert res.offset == 0
    assert res.limit == 2
    all_res = get_provider_models("groq", offset=0, limit=1000, home=home)
    assert all_res.total == len(all_res.models)
    assert "llama-3.3-70b-versatile" in [m.id for m in all_res.models]


def test_get_provider_models_offset_paginates(tmp_path):
    home = _home(tmp_path)
    first = get_provider_models("groq", offset=0, limit=1, home=home)
    second = get_provider_models("groq", offset=1, limit=1, home=home)
    assert first.total == second.total
    assert first.models and second.models
    assert first.models[0].id != second.models[0].id


def test_get_provider_models_unknown_empty(tmp_path):
    res = get_provider_models("nonexistent", home=_home(tmp_path))
    assert res.total == 0
    assert res.models == []


def test_get_provider_list_after_auth_and_model(tmp_path):
    home = _home(tmp_path)
    result = get_provider_list(home)
    assert "groq" in [p.id for p in result.all]
    save_provider_config(
        home,
        provider="groq",
        api_key="gsk_secretkey123",
        model="",
        base_url="",
        max_tokens=DEFAULT_LLM_MAX_TOKENS,
        temperature=DEFAULT_LLM_TEMPERATURE,
        set_active=False,
    )
    info = get_provider_list(home)
    groq_info = next(p for p in info.all if p.id == "groq")
    assert groq_info.has_api_key is True
    assert groq_info.api_key_masked
    assert "gsk_secretkey123" not in groq_info.api_key_masked
    assert groq_info.validation_status == "configured"
    assert groq_info.is_active is False
    result = get_provider_list(home)
    assert "groq" in result.connected
    info = set_provider_model(
        "groq", ProviderModelRequest(model="llama-3.3-70b-versatile"), home=home
    )
    assert info.model == "llama-3.3-70b-versatile"
    assert info.is_active is True
    assert result.active != "groq"
    result2 = get_provider_list(home)
    assert result2.active == "groq"
    groq = next(p for p in result2.all if p.id == "groq")
    assert "llama-3.3-70b-versatile" in groq.models


async def test_upsert_user_model_idempotent(tmp_path):
    from server.storage.provider_config import upsert_provider_models

    home = _home(tmp_path)
    upsert_provider_models(
        home,
        "openai_compatible",
        models=[
            {"id": "my-model", "name": "My Model", "context_window": 32000},
            {"id": "other-model", "name": "Other Model", "context_window": 64000},
        ],
    )
    _, providers = read_provider_config_full(home)
    ids = [m["id"] for m in providers["openai_compatible"]["models"]]
    assert "my-model" in ids
    assert "other-model" in ids
    upsert_provider_models(
        home,
        "openai_compatible",
        models=[{"id": "my-model", "name": "My Model V2", "context_window": 48000}],
    )
    _, providers = read_provider_config_full(home)
    models = {m["id"]: m for m in providers["openai_compatible"]["models"]}
    assert len(models) == 2
    assert models["my-model"]["name"] == "My Model V2"
    assert models["my-model"]["context_window"] == 48000


async def test_validate_unknown_provider():
    result = await validate_provider_collect("does_not_exist")
    assert result.valid is False
    assert result.error.code == "UNKNOWN_PROVIDER"


async def test_validate_missing_base_url(tmp_path, monkeypatch):
    import copy

    from server.storage.catalog_compat import invalidate_catalog_cache

    home = _home(tmp_path)

    def fake_catalog(_home=None):
        # Deep-copy: load_catalog() returns shared/cached dicts; mutating them
        # would poison every later consumer in the same process.
        catalog = copy.deepcopy(load_catalog(home))
        catalog["providers"]["groq"] = dict(catalog["providers"]["groq"], base_url="")
        return catalog

    monkeypatch.setattr("server.providers.validation.load_catalog", fake_catalog)
    try:
        result = await validate_provider_collect(
            "groq", api_key="gsk-x", model="llama-3.3-70b-versatile"
        )
    finally:
        invalidate_catalog_cache()
    assert result.valid is False
    assert result.error.code == "MISSING_BASE_URL"


async def test_validate_invalid_base_url(tmp_path):
    _home(tmp_path)
    result = await validate_provider_collect(
        "groq", api_key="gsk-x", base_url="ftp://bad", model="llama-3.3-70b-versatile"
    )
    assert result.valid is False
    assert result.error.code == "INVALID_BASE_URL"


async def test_validate_missing_api_key(tmp_path):
    _home(tmp_path)
    result = await validate_provider_collect(
        "groq", base_url=GROQ_URL, model="llama-3.3-70b-versatile"
    )
    assert result.valid is False
    assert result.error.code == "MISSING_API_KEY"


async def test_validate_connection_failure(tmp_path):
    _home(tmp_path)
    result = await validate_provider_collect(
        "groq",
        api_key="gsk-x",
        base_url="http://127.0.0.1:1",
        model="llama-3.3-70b-versatile",
    )
    assert result.valid is False
    assert result.error.code == "CONNECTION_FAILED"
    keys = [s.key for s in result.steps]
    assert keys == list(STEP_LABELS.keys())
    config_step = next(s for s in result.steps if s.key == "config")
    assert config_step.status.value == "success"


async def test_validate_auth_probe_rejects_bad_key(tmp_path, monkeypatch):
    _home(tmp_path)

    class _FakeResponse:
        status_code = 200

        def json(self):
            return {"data": []}

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, *args, **kwargs):
            return _FakeResponse()

    class _FakeProvider:
        def __init__(self, *args, **kwargs):
            pass

        async def complete(self, *args, **kwargs):
            raise type("AuthenticationError", (Exception,), {})("Authentication failed")

    monkeypatch.setattr("server.providers.validation.httpx.AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr("server.providers.validation.LLMProvider", _FakeProvider)
    result = await validate_provider_collect(
        "groq",
        api_key="gsk-bad",
        base_url=GROQ_URL,
        model="llama-3.3-70b-versatile",
    )
    assert result.valid is False
    assert result.error.code == "AUTH_FAILED"
    auth = next(s for s in result.steps if s.key == "auth")
    assert auth.status.value == "failed"


async def test_validate_auth_probe_accepts_key_on_model_error(tmp_path, monkeypatch):
    _home(tmp_path)

    class _FakeResponse:
        status_code = 200

        def json(self):
            return {"data": []}

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, *args, **kwargs):
            return _FakeResponse()

    class _FakeProvider:
        def __init__(self, *args, **kwargs):
            pass

        async def complete(self, *args, **kwargs):
            raise RuntimeError("404 - model not found")

    monkeypatch.setattr("server.providers.validation.httpx.AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr("server.providers.validation.LLMProvider", _FakeProvider)
    result = await validate_provider_collect(
        "groq",
        api_key="gsk-ok",
        base_url=GROQ_URL,
        model="llama-3.3-70b-versatile",
    )
    assert result.valid is False
    assert result.error.code == "SMOKE_TEST_FAILED"
    auth = next(s for s in result.steps if s.key == "auth")
    assert auth.status.value == "success"


async def test_validate_stream_emits_step_events(tmp_path):
    _home(tmp_path)
    events = []
    async for ev in validate_provider(
        "groq",
        api_key="gsk-x",
        base_url="http://127.0.0.1:1",
        model="llama-3.3-70b-versatile",
    ):
        events.append(ev)
    types = [e["type"] for e in events]
    assert "step" in types
    assert "result" in types
    result = next(e for e in events if e["type"] == "result")
    assert result["valid"] is False


class TestExtractCachedTokens:
    def _extract(self):
        from server.providers.llm_provider import _extract_cached_tokens

        return _extract_cached_tokens

    def test_none_returns_zero(self):
        assert self._extract()(None) == 0

    def test_empty_and_unrelated_usage_returns_zero(self):
        f = self._extract()
        assert f({}) == 0
        assert f({"prompt_tokens": 100}) == 0

    def test_openai_prompt_tokens_details_dict(self):
        f = self._extract()
        assert f({"prompt_tokens_details": {"cached_tokens": 42}}) == 42

    def test_openai_prompt_tokens_details_object(self):
        f = self._extract()

        class _Details:
            cached_tokens = 7

        class _Usage:
            prompt_tokens_details = _Details()

        assert f(_Usage()) == 7

    def test_gemini_snake_and_camel_top_level(self):
        f = self._extract()
        assert f({"cached_content_token_count": 99}) == 99

        class _Usage:
            cachedContentTokenCount = 88

        assert f(_Usage()) == 88

    def test_does_not_misread_cache_creation_tokens(self):
        f = self._extract()
        assert f({"cache_creation_input_tokens": 500}) == 0

        class _Usage:
            cache_creation_input_tokens = 500

        assert f(_Usage()) == 0

    def test_zero_reported_hits_returns_zero(self):
        f = self._extract()
        assert f({"prompt_tokens_details": {"cached_tokens": 0}}) == 0
