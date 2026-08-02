"""Tests for the provider configuration redesign — mask, list, auth, model, validate."""

import pytest

from server.api.provider_validation import (
    get_provider_list,
    set_provider_auth,
    set_provider_model,
)
from server.api.schemas import ProviderAuthRequest, ProviderModelRequest
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


def test_get_provider_list_without_db(tmp_path):
    result = get_provider_list(db_path=str(tmp_path / "missing.db"))
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


def test_get_provider_list_after_auth_and_model(tmp_path):
    db_file = str(tmp_path / "test.db")
    _bootstrap_db(db_file)

    result = get_provider_list(db_path=db_file)
    assert "groq" in [p.id for p in result.all]

    info = set_provider_auth("groq", ProviderAuthRequest(api_key="gsk_secretkey123"), db_path=db_file)
    assert info.has_api_key is True
    assert info.api_key_masked
    assert "gsk_secretkey123" not in info.api_key_masked
    assert info.validation_status == "configured"
    assert info.is_active is False

    result = get_provider_list(db_path=db_file)
    assert "groq" in result.connected

    info = set_provider_model("groq", ProviderModelRequest(model="llama-3.3-70b-versatile"), db_path=db_file)
    assert info.model == "llama-3.3-70b-versatile"
    assert info.is_active is True
    assert result.default["active"] != "groq"  # not active yet at list snapshot time
    result2 = get_provider_list(db_path=db_file)
    assert result2.default["active"] == "groq"
    groq = next(p for p in result2.all if p.id == "groq")
    assert "llama-3.3-70b-versatile" in groq.models


def test_set_provider_auth_creates_row_with_catalog_metadata(tmp_path):
    db_file = str(tmp_path / "test.db")
    _bootstrap_db(db_file)
    info = set_provider_auth("custom", ProviderAuthRequest(api_key=""), db_path=db_file)
    assert info.name == "Custom OpenAI-Compatible"
    assert info.swatch
    assert info.requires_api_key is False


def test_set_provider_auth_unknown_provider(tmp_path):
    db_file = str(tmp_path / "test.db")
    _bootstrap_db(db_file)
    with pytest.raises(ValueError):
        set_provider_auth("does_not_exist", ProviderAuthRequest(api_key="sk-x"), db_path=db_file)


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
        catalog = load_catalog()
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
            {"id": "my-model", "name": "My Model", "context_window": 32000, "description": "", "is_default": False},
            {"id": "other-model", "name": "Other Model", "context_window": 64000, "description": "", "is_default": False},
        ],
        db_path=db_file,
    )
    active, providers = read_provider_config_full(db_path=db_file)
    ids = [m["id"] for m in providers["custom"]["models"]]
    assert "my-model" in ids
    assert "other-model" in ids

    provider_config_repo.upsert_provider_models(
        provider="custom",
        models=[{"id": "my-model", "name": "My Model V2", "context_window": 48000, "description": "", "is_default": False}],
        db_path=db_file,
    )
    active, providers = read_provider_config_full(db_path=db_file)
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


async def test_validate_missing_base_url(monkeypatch):
    def fake_catalog():
        catalog = load_catalog()
        catalog["providers"]["openai"] = dict(catalog["providers"]["openai"], base_url="")
        return catalog

    monkeypatch.setattr("server.providers.validation.load_catalog", fake_catalog)
    result = await validate_provider_collect("openai", api_key="sk-x", model="gpt-4o-mini", db_path=":memory:")
    assert result.valid is False
    assert result.error.code == "MISSING_BASE_URL"


async def test_validate_invalid_base_url():
    result = await validate_provider_collect(
        "openai", api_key="sk-x", base_url="ftp://bad", model="gpt-4o-mini", db_path=":memory:"
    )
    assert result.valid is False
    assert result.error.code == "INVALID_BASE_URL"


async def test_validate_missing_api_key():
    result = await validate_provider_collect(
        "openai", base_url="https://api.openai.com/v1", model="gpt-4o-mini", db_path=":memory:"
    )
    assert result.valid is False
    assert result.error.code == "MISSING_API_KEY"


async def test_validate_connection_failure():
    result = await validate_provider_collect(
        "openai", api_key="sk-x", base_url="http://127.0.0.1:1", model="gpt-4o-mini", db_path=":memory:"
    )
    assert result.valid is False
    assert result.error.code == "CONNECTION_FAILED"
    keys = [s.key for s in result.steps]
    assert keys == list(STEP_LABELS.keys())
    config_step = next(s for s in result.steps if s.key == "config")
    assert config_step.status.value == "success"


async def test_validate_stream_emits_step_events():
    events = []
    async for ev in validate_provider(
        "openai", api_key="sk-x", base_url="http://127.0.0.1:1", model="gpt-4o-mini", db_path=":memory:"
    ):
        events.append(ev)
    types = [e["type"] for e in events]
    assert "step" in types
    assert "result" in types
    result = [e for e in events if e["type"] == "result"][0]
    assert result["valid"] is False
