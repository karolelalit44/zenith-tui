
from __future__ import annotations
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any
from sqlalchemy import create_engine, event, inspect, select, text, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session as SASession
from sqlalchemy.orm import sessionmaker
from server.persistence.connection import resolve_db_path
from server.persistence.models import (AppSettingRecord, CatalogModelRecord, CatalogProviderRecord, ProviderModelRecord, ProviderRecord)

logger = logging.getLogger(__name__)

MODEL_STORE_KEY = "model_store"

EMPTY_CATALOG: dict[str, Any] = {"version": 1, "providers": {}}


def mask_api_key(key: str | None) -> str:
    if not key:
        return ""
    key = key.strip()
    if len(key) <= 8:
        return "***" + key[-4:]
    return key[:8] + "***" + key[-4:]


def _set_pragmas(dbapi_connection, connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


def _engine(db_path: str) -> Engine:
    engine = create_engine(f"sqlite:///{Path(db_path).resolve()}")
    event.listen(engine, "connect", _set_pragmas)
    return engine


def _session(engine: Engine) -> sessionmaker[SASession]:
    return sessionmaker(engine, expire_on_commit=False)


def _has_table(engine: Engine, name: str) -> bool:
    try:
        return inspect(engine).has_table(name)
    except Exception:
        return False


def read_active_provider(db_path: str | None = None) -> str | None:
    db_path = db_path or resolve_db_path()
    if not Path(db_path).exists():
        return None
    engine = _engine(db_path)
    try:
        if not _has_table(engine, "app_settings"):
            return None
        with _session(engine)() as s:
            value = s.execute(select(AppSettingRecord.value).where(AppSettingRecord.key == "active_provider")).scalar_one_or_none()
            return value if value else None
    except Exception as e:
        logger.warning("read_active_provider failed: %s", e)
        return None
    finally:
        engine.dispose()


def read_providers(db_path: str | None = None) -> dict[str, dict[str, Any]]:
    db_path = db_path or resolve_db_path()
    if not Path(db_path).exists():
        return {}
    engine = _engine(db_path)
    try:
        if not _has_table(engine, "providers"):
            return {}
        with _session(engine)() as s:
            rows = s.execute(select(ProviderRecord)).scalars().all()
        result = {}
        for r in rows:
            result[r.id] = {"api_key": r.api_key, "model": r.model, "base_url": r.base_url, "max_tokens": r.max_tokens, "temperature": r.temperature, "is_active": bool(r.is_active)}
        return result
    except Exception as e:
        logger.warning("read_providers failed: %s", e)
        return {}
    finally:
        engine.dispose()


def read_provider_config_full(db_path: str | None = None) -> tuple[str, dict[str, dict[str, Any]]]:
    db_path = db_path or resolve_db_path()
    if not Path(db_path).exists():
        return "", {}

    from server.persistence.repositories import load_catalog

    engine = _engine(db_path)
    try:
        if not _has_table(engine, "providers"):
            return "", {}
        with _session(engine)() as s:
            active = s.execute(select(AppSettingRecord.value).where(AppSettingRecord.key == "active_provider")).scalar_one_or_none()
            active = active or ""

            p_rows = s.execute(select(ProviderRecord)).scalars().all()
            result_providers: dict[str, dict[str, Any]] = {}
            for r in p_rows:
                pid = r.id
                m_rows = (s.execute(select(ProviderModelRecord) .where(ProviderModelRecord.provider_id == pid) .order_by(ProviderModelRecord.is_default.desc(), ProviderModelRecord.name)) .scalars() .all())

                catalog = load_catalog()
                catalog_models = {m["id"]: m for m in catalog.get("providers", {}).get(pid, {}).get("models", [])}

                enriched_models = []
                for m in m_rows:
                    cat = catalog_models.get(m.id, {})
                    enriched_models.append({"id": m.id, "name": m.name, "context_window": m.context_window, "description": m.description, "is_default": m.is_default, "parameters": cat.get("parameters"), "architecture": cat.get("architecture"), "input_modalities": cat.get("input_modalities"), "output_modalities": cat.get("output_modalities"), "tags": cat.get("tags"), "model_capabilities": cat.get("model_capabilities"), "speed_tier": cat.get("speed_tier"), "best_for": cat.get("best_for")})

                p_dict = {"id": r.id, "name": r.name, "description": r.description, "api_key": mask_api_key(r.api_key), "has_api_key": bool(r.api_key and r.api_key.strip()), "api_key_masked": mask_api_key(r.api_key), "model": r.model, "base_url": r.base_url, "max_tokens": r.max_tokens, "temperature": r.temperature, "is_active": bool(r.is_active), "swatch_json": r.swatch_json, "adapter_type": r.adapter_type, "capabilities_json": r.capabilities_json, "api_key_prefix": r.api_key_prefix, "updated_at": r.updated_at, "models": enriched_models, "swatch": json.loads(r.swatch_json or "[]")}
                result_providers[pid] = p_dict

        return active, result_providers
    except Exception as e:
        logger.warning("read_provider_config_full failed: %s", e)
        return "", {}
    finally:
        engine.dispose()


def save_provider_config(provider: str, api_key: str, model: str, base_url: str, max_tokens: int, temperature: float, db_path: str | None = None, set_active: bool = True) -> None:
    db_path = db_path or resolve_db_path()
    now = datetime.now().isoformat()

    from server.persistence.repositories import load_catalog

    catalog_entry = load_catalog().get("providers", {}).get(provider) or {}

    engine = _engine(db_path)
    try:
        with _session(engine)() as s:
            existing = s.get(ProviderRecord, provider)
            if existing:
                new_key = api_key if api_key.strip() else existing.api_key
                new_model = model if model.strip() else existing.model
                new_base = base_url if base_url.strip() else existing.base_url
                existing.api_key = new_key
                existing.model = new_model
                existing.base_url = new_base
                existing.max_tokens = max_tokens
                existing.temperature = temperature
                existing.updated_at = now
            else:
                s.add(ProviderRecord(id=provider, name=catalog_entry.get("name") or provider.title(), description=catalog_entry.get("description", ""), api_key=api_key, model=model, base_url=base_url, max_tokens=max_tokens, temperature=temperature, is_active=False, swatch_json=json.dumps(catalog_entry.get("swatch", [])), adapter_type=catalog_entry.get("adapter", "openai_compat"), capabilities_json=json.dumps(catalog_entry.get("capabilities", {})), api_key_prefix=catalog_entry.get("api_key_prefix"), updated_at=now))
            if set_active:
                s.execute(update(ProviderRecord).values(is_active=False))
                s.execute(update(ProviderRecord) .where(ProviderRecord.id == provider) .values(is_active=True))
                s.execute(text("INSERT OR REPLACE INTO app_settings (key, value) VALUES (:key, :value)"), {"key": "active_provider", "value": provider})
            s.commit()
    except Exception as e:
        logger.warning("save_provider_config failed: %s", e)
        raise
    finally:
        engine.dispose()


def upsert_provider_models(provider: str, models: list[dict[str, Any]], db_path: str | None = None) -> None:
    if not models:
        return
    db_path = db_path or resolve_db_path()
    engine = _engine(db_path)
    try:
        with _session(engine)() as s:
            s.execute(text(""" INSERT OR IGNORE INTO providers (id, name, description, api_key, model, base_url, is_active, swatch_json, capabilities_json, api_key_prefix, updated_at) VALUES (:id, :name, '', '', '', '', 0, '[]', '{}', NULL, :now) """), {"id": provider, "name": provider.title(), "now": datetime.now().isoformat()})
            for m in models:
                mid = m.get("id")
                if not mid:
                    continue
                s.execute(text(""" INSERT INTO provider_models (id, provider_id, name, context_window, description, is_default) VALUES (:id, :provider_id, :name, :context_window, :description, :is_default) ON CONFLICT(provider_id, id) DO UPDATE SET name = excluded.name, context_window = excluded.context_window, description = excluded.description, is_default = excluded.is_default """), {"id": mid, "provider_id": provider, "name": m.get("name") or mid, "context_window": int(m.get("context_window") or 128000), "description": m.get("description") or "", "is_default": 1 if m.get("is_default") else 0})
            s.commit()
    except Exception as e:
        logger.warning("upsert_provider_models failed: %s", e)
        raise
    finally:
        engine.dispose()


def read_catalog(db_path: str | None = None) -> dict[str, Any]:
    db_path = db_path or resolve_db_path()
    if not Path(db_path).exists():
        return EMPTY_CATALOG
    engine = _engine(db_path)
    try:
        if not _has_table(engine, "catalog_providers"):
            return EMPTY_CATALOG
        with _session(engine)() as s:
            p_rows = (s.execute(select(CatalogProviderRecord).order_by(CatalogProviderRecord.sort_order)) .scalars() .all())
            if not p_rows:
                return EMPTY_CATALOG
            providers: dict[str, dict[str, Any]] = {}
            for r in p_rows:
                m_rows = (s.execute(select(CatalogModelRecord) .where(CatalogModelRecord.provider_id == r.id) .order_by(CatalogModelRecord.is_default.desc(), CatalogModelRecord.name)) .scalars() .all())
                models = []
                for m in m_rows:
                    models.append({"id": m.id, "name": m.name, "description": m.description, "context_window": m.context_window, "parameters": m.parameters, "architecture": m.architecture, "input_modalities": json.loads(m.input_modalities or "[]"), "output_modalities": json.loads(m.output_modalities or "[]"), "tags": json.loads(m.tags or "[]"), "model_capabilities": json.loads(m.model_capabilities_json or "{}"), "speed_tier": m.speed_tier, "best_for": json.loads(m.best_for or "[]"), "pricing": json.loads(m.pricing_json or "{}"), "is_default": bool(m.is_default), "tokenizer": m.tokenizer, "prompt_tier": m.prompt_tier})
                providers[r.id] = {"id": r.id, "name": r.name, "description": r.description, "adapter": r.adapter, "litellm_prefix": r.litellm_prefix, "default_model": r.default_model, "base_url": r.base_url, "api_key_prefix": r.api_key_prefix, "requires_api_key": bool(r.requires_api_key), "swatch": json.loads(r.swatch_json or "[]"), "capabilities": json.loads(r.capabilities_json or "{}"), "config_fields": json.loads(r.config_fields_json or "[]"), "env_keys": json.loads(r.env_keys_json or "[]"), "is_popular": bool(r.is_popular), "base_url_style": r.base_url_style, "supports_prompt_caching": bool(r.supports_prompt_caching), "supports_thinking_headers": bool(r.supports_thinking_headers), "custom_flow": bool(r.custom_flow), "models": models}
            return {"version": 1, "providers": providers}
    except Exception as e:
        logger.warning("read_catalog failed: %s", e)
        return EMPTY_CATALOG
    finally:
        engine.dispose()


def read_model_store(db_path: str | None = None) -> dict[str, Any]:
    db_path = db_path or resolve_db_path()
    if not Path(db_path).exists():
        return {}
    engine = _engine(db_path)
    try:
        if not _has_table(engine, "app_settings"):
            return {}
        with _session(engine)() as s:
            raw = s.execute(select(AppSettingRecord.value).where(AppSettingRecord.key == MODEL_STORE_KEY)).scalar_one_or_none()
            if not raw:
                return {}
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
            return {}
    except Exception as e:
        logger.warning("read_model_store failed: %s", e)
        return {}
    finally:
        engine.dispose()


def write_model_store(db_path: str | None, data: dict[str, Any]) -> None:
    db_path = db_path or resolve_db_path()
    if not Path(db_path).exists():
        return
    payload = {"current": data.get("current") or None, "recent": [s for s in (data.get("recent") or []) if isinstance(s, dict)], "favorite": [s for s in (data.get("favorite") or []) if isinstance(s, dict)]}
    engine = _engine(db_path)
    try:
        with _session(engine)() as s:
            if not payload["current"] and not payload["recent"] and not payload["favorite"]:
                s.execute(text("DELETE FROM app_settings WHERE key = :key"), {"key": MODEL_STORE_KEY})
            else:
                s.execute(text("INSERT OR REPLACE INTO app_settings (key, value) VALUES (:key, :value)"), {"key": MODEL_STORE_KEY, "value": json.dumps(payload)})
            s.commit()
    except Exception as e:
        logger.warning("write_model_store failed: %s", e)
    finally:
        engine.dispose()
