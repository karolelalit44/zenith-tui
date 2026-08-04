"""Tests for the provider configuration redesign — mask, list, model, validate."""

from server.api.provider_validation import (
    get_provider_list,
    set_provider_model,
)
from server.api.schemas import ProviderModelRequest
from server.persistence import provider_config_repo
from server.persistence.connection import Database
from server.persistence.provider_config_repo import mask_api_key, read_provider_config_full
from server.persistence.repositories import ProviderRepositoryDB, load_catalog
from server.providers.validation import STEP_LABELS, validate_provider, validate_provider_collect


def _bootstrap_db(db_path: str) -> None:
    from server.persistence.startup import DatabaseStartupService

    DatabaseStartupService(db_path).run()


# ---------------------------------------------------------------------------
# Masking
# ---------------------------------------------------------------------------


def test_mask_api_key():
    assert mask_api_key(None) == ""
    assert mask_api_key("") == ""
    assert mask_api_key("abcdefgh") == "***efgh"
    assert mask_api_key("sk-or-v1-1234abcd5678efgh") == "sk-or-v1***efgh"
    assert "1234abcd" not in mask_api_key("sk-or-v1-1234abcd5678efgh")


def test_read_provider_config_full_masks_key(tmp_path):
    db_file = str(tmp_path / "test.db")
    _bootstrap_db(db_file)
    provider_config_repo.save_provider_config(
        provider="openai",
        api_key="sk-supersecretkey-xyz",
        model="gpt-4o-mini",
        base_url="https://api.openai.com/v1",
        max_tokens=4096,
        temperature=0.7,
        db_path=db_file,
    )
    active, providers = read_provider_config_full(db_path=db_file)
    assert active == "openai"
    p = providers["openai"]
    assert p["api_key_masked"] == "sk-super***-xyz"
    assert p["has_api_key"] is True
    assert p["api_key"] == p["api_key_masked"]
    assert "sk-supersecretkey-xyz" not in p["api_key"]


# ---------------------------------------------------------------------------
# Provider list
# ---------------------------------------------------------------------------


def test_get_provider_list_from_migrated_db(tmp_path):
    # The catalog is SQL-only: a migrated DB is required for the provider list.
    db_file = str(tmp_path / "test.db")
    _bootstrap_db(db_file)

    result = get_provider_list(db_path=db_file)
    ids = [p.id for p in result.all]
    assert len(ids) >= 8
    assert "nvidia" in ids
    assert "openai_compatible" in ids
    assert "custom" in ids
    assert result.connected == []
    nvidia = next(p for p in result.all if p.id == "nvidia")
    assert nvidia.validation_status == "unconfigured"
    assert nvidia.has_api_key is False
    assert nvidia.config_fields
    assert nvidia.models
    # SQL-driven behavior flags surface on ProviderInfo
    assert nvidia.is_popular is True
    assert nvidia.base_url_style == ""
    assert next(p for p in result.all if p.id == "openai_compatible").custom_flow is True
    assert next(p for p in result.all if p.id == "tokenrouter").base_url_style == "tokenrouter"
    assert next(p for p in result.all if p.id == "anthropic").supports_prompt_caching is True
    assert next(p for p in result.all if p.id == "anthropic").supports_thinking_headers is True


def test_get_provider_list_missing_db_empty():
    # Without a migrated DB there is no catalog (no provider names in Python).
    result = get_provider_list(db_path=":memory:")
    assert result.all == []
    assert result.connected == []


def test_get_provider_list_after_auth_and_model(tmp_path):
    db_file = str(tmp_path / "test.db")
    _bootstrap_db(db_file)

    result = get_provider_list(db_path=db_file)
    assert "groq" in [p.id for p in result.all]

    provider_config_repo.save_provider_config(
        provider="groq",
        api_key="gsk_secretkey123",
        model="",
        base_url="",
        max_tokens=4096,
        temperature=0.7,
        db_path=db_file,
        set_active=False,
    )
    info = get_provider_list(db_path=db_file)
    groq_info = next(p for p in info.all if p.id == "groq")
    assert groq_info.has_api_key is True
    assert groq_info.api_key_masked
    assert "gsk_secretkey123" not in groq_info.api_key_masked
    assert groq_info.validation_status == "configured"
    assert groq_info.is_active is False

    result = get_provider_list(db_path=db_file)
    assert "groq" in result.connected

    info = set_provider_model(
        "groq", ProviderModelRequest(model="llama-3.3-70b-versatile"), db_path=db_file
    )
    assert info.model == "llama-3.3-70b-versatile"
    assert info.is_active is True
    assert result.active != "groq"  # not active yet at list snapshot time
    result2 = get_provider_list(db_path=db_file)
    assert result2.active == "groq"
    groq = next(p for p in result2.all if p.id == "groq")
    assert "llama-3.3-70b-versatile" in groq.models


# ---------------------------------------------------------------------------
# Idempotent seeding reconcile
# ---------------------------------------------------------------------------


async def test_ensure_seeded_reconcile(tmp_path):
    db_file = str(tmp_path / "test.db")
    _bootstrap_db(db_file)
    db = Database(db_file)
    await db.connect()
    try:
        repo = ProviderRepositoryDB(db)
        await repo.ensure_seeded()
        catalog = load_catalog(db_file)
        expected = list(catalog["providers"].keys())

        providers = await repo.list_providers()
        assert sorted(providers.keys()) == sorted(expected)
        for pid in expected:
            assert providers[pid]["models"], f"provider {pid} has no seeded models"

        # Second run must be a no-op (no duplicate rows).
        before = {pid: len(p["models"]) for pid, p in providers.items()}
        await repo.ensure_seeded()
        providers2 = await repo.list_providers()
        assert sorted(providers2.keys()) == sorted(expected)
        assert {pid: len(p["models"]) for pid, p in providers2.items()} == before
    finally:
        await db.close()


async def test_upsert_provider_models_idempotent(tmp_path):
    db_file = str(tmp_path / "test.db")
    _bootstrap_db(db_file)
    provider_config_repo.upsert_provider_models(
        provider="custom",
        models=[
            {
                "id": "my-model",
                "name": "My Model",
                "context_window": 32000,
                "description": "",
                "is_default": False,
            },
            {
                "id": "other-model",
                "name": "Other Model",
                "context_window": 64000,
                "description": "",
                "is_default": False,
            },
        ],
        db_path=db_file,
    )
    _, providers = read_provider_config_full(db_path=db_file)
    ids = [m["id"] for m in providers["custom"]["models"]]
    assert "my-model" in ids
    assert "other-model" in ids

    provider_config_repo.upsert_provider_models(
        provider="custom",
        models=[
            {
                "id": "my-model",
                "name": "My Model V2",
                "context_window": 48000,
                "description": "",
                "is_default": False,
            }
        ],
        db_path=db_file,
    )
    _, providers = read_provider_config_full(db_path=db_file)
    models = {m["id"]: m for m in providers["custom"]["models"]}
    assert len(models) == 2  # no dupes
    assert models["my-model"]["name"] == "My Model V2"
    assert models["my-model"]["context_window"] == 48000


# ---------------------------------------------------------------------------
# Validation pipeline (offline failure paths)
# ---------------------------------------------------------------------------


async def test_validate_unknown_provider():
    result = await validate_provider_collect("does_not_exist", db_path=":memory:")
    assert result.valid is False
    assert result.error.code == "UNKNOWN_PROVIDER"


async def test_validate_missing_base_url(tmp_path, monkeypatch):
    db_file = str(tmp_path / "test.db")
    _bootstrap_db(db_file)

    def fake_catalog(db_path=None):
        catalog = load_catalog(db_path)
        catalog["providers"]["openai"] = dict(catalog["providers"]["openai"], base_url="")
        return catalog

    monkeypatch.setattr("server.providers.validation.load_catalog", fake_catalog)
    result = await validate_provider_collect(
        "openai", api_key="sk-x", model="gpt-4o-mini", db_path=db_file
    )
    assert result.valid is False
    assert result.error.code == "MISSING_BASE_URL"


async def test_validate_invalid_base_url(tmp_path):
    db_file = str(tmp_path / "test.db")
    _bootstrap_db(db_file)
    result = await validate_provider_collect(
        "openai", api_key="sk-x", base_url="ftp://bad", model="gpt-4o-mini", db_path=db_file
    )
    assert result.valid is False
    assert result.error.code == "INVALID_BASE_URL"


async def test_validate_missing_api_key(tmp_path):
    db_file = str(tmp_path / "test.db")
    _bootstrap_db(db_file)
    result = await validate_provider_collect(
        "openai", base_url="https://api.openai.com/v1", model="gpt-4o-mini", db_path=db_file
    )
    assert result.valid is False
    assert result.error.code == "MISSING_API_KEY"


async def test_validate_connection_failure(tmp_path):
    db_file = str(tmp_path / "test.db")
    _bootstrap_db(db_file)
    result = await validate_provider_collect(
        "openai",
        api_key="sk-x",
        base_url="http://127.0.0.1:1",
        model="gpt-4o-mini",
        db_path=db_file,
    )
    assert result.valid is False
    assert result.error.code == "CONNECTION_FAILED"
    keys = [s.key for s in result.steps]
    assert keys == list(STEP_LABELS.keys())
    config_step = next(s for s in result.steps if s.key == "config")
    assert config_step.status.value == "success"


async def test_validate_auth_probe_rejects_bad_key(tmp_path, monkeypatch):
    db_file = str(tmp_path / "test.db")
    _bootstrap_db(db_file)

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
        "openai",
        api_key="sk-bad",
        base_url="https://api.openai.com/v1",
        model="gpt-4o-mini",
        db_path=db_file,
    )
    assert result.valid is False
    assert result.error.code == "AUTH_FAILED"
    auth = next(s for s in result.steps if s.key == "auth")
    assert auth.status.value == "failed"


async def test_validate_auth_probe_accepts_key_on_model_error(tmp_path, monkeypatch):
    db_file = str(tmp_path / "test.db")
    _bootstrap_db(db_file)

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
            raise Exception("404 - model not found")  # noqa: TRY002 - test stub

    monkeypatch.setattr("server.providers.validation.httpx.AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr("server.providers.validation.LLMProvider", _FakeProvider)
    result = await validate_provider_collect(
        "openai",
        api_key="sk-ok",
        base_url="https://api.openai.com/v1",
        model="gpt-4o-mini",
        db_path=db_file,
    )
    assert result.valid is False
    assert result.error.code == "SMOKE_TEST_FAILED"
    auth = next(s for s in result.steps if s.key == "auth")
    assert auth.status.value == "success"


async def test_validate_stream_emits_step_events(tmp_path):
    db_file = str(tmp_path / "test.db")
    _bootstrap_db(db_file)
    events = []
    async for ev in validate_provider(
        "openai",
        api_key="sk-x",
        base_url="http://127.0.0.1:1",
        model="gpt-4o-mini",
        db_path=db_file,
    ):
        events.append(ev)
    types = [e["type"] for e in events]
    assert "step" in types
    assert "result" in types
    result = next(e for e in events if e["type"] == "result")
    assert result["valid"] is False
