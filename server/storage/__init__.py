"""File-based persistence layer — replaces the SQLite database entirely.

Layout:

    <home>/user_profile.json     identity, API keys (sole secret store), preferences
    <home>/zenith_catalog.json   single provider catalog (providers + nested
                                 models) — no secrets
    <home>/projects/<slug>/      one folder per workspace (Claude Code style);
                                 each session is ONE append-only JSONL:
                                 <session-id>.jsonl  (header + meta/stats/
                                 msg/sync/usage/checkpoint/wsfile records)

The home directory defaults to ``~/.zenith`` and is overridden by
``ZENITH_HOME`` (tests/e2e use temp dirs).
"""

from .atomic import (
    append_jsonl_sync,
    read_json,
    read_jsonl,
    rewrite_jsonl_atomic,
    write_json_atomic,
)
from .builtin_seed import PROVIDERS, SEED_VERSION
from .catalog_store import (
    CatalogValidationError,
    ensure_materialized,
    invalidate_catalog_cache,
    load_catalog,
    read_model_entries,
    read_providers,
    upsert_model,
    upsert_provider,
)
from .paths import HOME_ENV_VAR, StorageHome, default_home, resolve_home
from .profile_store import (
    get_api_key,
    load_profile,
    mask_api_key,
    public_profile,
    save_profile,
    set_api_key,
    update_preferences,
)
from .session_store import (
    FileCheckpointRepository,
    FileMessageRepository,
    FileSessionRepository,
    FileSyncEventRepository,
)
from .usage_store import FileTokenUsageRepository

__all__ = [
    "HOME_ENV_VAR",
    "PROVIDERS",
    "SEED_VERSION",
    "CatalogValidationError",
    "FileCheckpointRepository",
    "FileMessageRepository",
    "FileSessionRepository",
    "FileSyncEventRepository",
    "FileTokenUsageRepository",
    "StorageHome",
    "append_jsonl_sync",
    "default_home",
    "ensure_materialized",
    "get_api_key",
    "invalidate_catalog_cache",
    "load_catalog",
    "load_profile",
    "mask_api_key",
    "public_profile",
    "read_json",
    "read_jsonl",
    "read_model_entries",
    "read_providers",
    "resolve_home",
    "rewrite_jsonl_atomic",
    "save_profile",
    "set_api_key",
    "update_preferences",
    "upsert_model",
    "upsert_provider",
    "write_json_atomic",
]
