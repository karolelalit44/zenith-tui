"""Provider config repository — sync + async DB access for provider/app_settings tables."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any

from db.connection import resolve_db_path

logger = logging.getLogger(__name__)


def _get_conn(db_path: str) -> tuple[sqlite3.Connection, sqlite3.Cursor]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn, conn.cursor()


def read_active_provider(db_path: str | None = None) -> str | None:
    db_path = db_path or resolve_db_path()
    if not Path(db_path).exists():
        return None
    try:
        conn, cur = _get_conn(db_path)
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='app_settings'")
        if not cur.fetchone():
            conn.close()
            return None
        cur.execute("SELECT value FROM app_settings WHERE key = 'active_provider'")
        row = cur.fetchone()
        conn.close()
        return row["value"] if row and row["value"] else None
    except Exception as e:
        logger.warning("read_active_provider failed: %s", e)
        return None


def read_providers(db_path: str | None = None) -> dict[str, dict[str, Any]]:
    db_path = db_path or resolve_db_path()
    if not Path(db_path).exists():
        return {}
    try:
        conn, cur = _get_conn(db_path)
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='providers'")
        if not cur.fetchone():
            conn.close()
            return {}
        cur.execute("SELECT * FROM providers")
        rows = cur.fetchall()
        conn.close()
        result = {}
        for r in rows:
            result[r["id"]] = {
                "api_key": r["api_key"],
                "model": r["model"],
                "base_url": r["base_url"],
                "max_tokens": r["max_tokens"],
                "temperature": r["temperature"],
                "is_active": bool(r["is_active"]),
            }
        return result
    except Exception as e:
        logger.warning("read_providers failed: %s", e)
        return {}


def read_provider_config_full(db_path: str | None = None) -> tuple[str, dict[str, dict[str, Any]]]:
    """Read full provider config with models, enriched with catalog data."""
    db_path = db_path or resolve_db_path()
    if not Path(db_path).exists():
        return "nvidia", {}

    from db.repository import load_catalog

    try:
        conn, cur = _get_conn(db_path)

        cur.execute("SELECT value FROM app_settings WHERE key = 'active_provider'")
        active_row = cur.fetchone()
        active = active_row["value"] if active_row else "nvidia"

        cur.execute("SELECT * FROM providers")
        p_rows = cur.fetchall()
        result_providers: dict[str, dict[str, Any]] = {}
        for r in p_rows:
            pid = r["id"]
            p_dict = dict(r)
            cur.execute(
                "SELECT id, name, context_window, description, is_default FROM provider_models WHERE provider_id = ?",
                (pid,),
            )
            m_rows = cur.fetchall()

            catalog = load_catalog()
            catalog_models = {
                m["id"]: m
                for m in catalog.get("providers", {}).get(pid, {}).get("models", [])
            }

            enriched_models = []
            for m in m_rows:
                m_dict = dict(m)
                cat = catalog_models.get(m_dict["id"], {})
                m_dict["parameters"] = cat.get("parameters")
                m_dict["architecture"] = cat.get("architecture")
                m_dict["input_modalities"] = cat.get("input_modalities")
                m_dict["output_modalities"] = cat.get("output_modalities")
                m_dict["tags"] = cat.get("tags")
                m_dict["model_capabilities"] = cat.get("model_capabilities")
                m_dict["speed_tier"] = cat.get("speed_tier")
                m_dict["best_for"] = cat.get("best_for")
                enriched_models.append(m_dict)

            p_dict["models"] = enriched_models
            import json
            p_dict["swatch"] = json.loads(p_dict.get("swatch_json", "[]"))
            result_providers[pid] = p_dict

        conn.close()
        return active, result_providers
    except Exception as e:
        logger.warning("read_provider_config_full failed: %s", e)
        return "nvidia", {}


def save_provider_config(
    provider: str,
    api_key: str,
    model: str,
    base_url: str,
    max_tokens: int,
    temperature: float,
    db_path: str | None = None,
) -> None:
    """Save provider config (upsert + set active)."""
    db_path = db_path or resolve_db_path()
    from datetime import datetime

    conn, cur = _get_conn(db_path)
    now = datetime.now().isoformat()

    cur.execute("SELECT * FROM providers WHERE id = ?", (provider,))
    existing = cur.fetchone()

    if existing:
        new_key = api_key if api_key.strip() else existing["api_key"]
        new_model = model if model.strip() else existing["model"]
        new_base = base_url if base_url.strip() else existing["base_url"]
        cur.execute(
            """
            UPDATE providers
            SET api_key = ?, model = ?, base_url = ?, max_tokens = ?, temperature = ?, updated_at = ?
            WHERE id = ?
            """,
            (new_key, new_model, new_base, max_tokens, temperature, now, provider),
        )
    else:
        cur.execute(
            """
            INSERT INTO providers (id, name, description, api_key, model, base_url, max_tokens, temperature, is_active, swatch_json, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, '[]', ?)
            """,
            (provider, provider.title(), "", api_key, model, base_url, max_tokens, temperature, now),
        )

    cur.execute("UPDATE providers SET is_active = 0")
    cur.execute("UPDATE providers SET is_active = 1 WHERE id = ?", (provider,))
    cur.execute(
        "INSERT OR REPLACE INTO app_settings (key, value) VALUES ('active_provider', ?)",
        (provider,),
    )
    conn.commit()
    conn.close()
