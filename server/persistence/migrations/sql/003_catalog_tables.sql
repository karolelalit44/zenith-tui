-- 003: reference provider catalog tables
--
-- SQL-backed provider catalog (the SQL source of truth for the provider list,
-- provider metadata, and curated model details). Replaces the old
-- provider_catalog.json reference file: /startup/providers and the config
-- loader enrich from these tables instead of a JSON file.
--
-- catalog_providers: static provider metadata (name, swatch, adapter,
-- config_fields, capabilities, ...). User state (API keys, active provider,
-- selected model) stays in the existing `providers` / `provider_models` /
-- `app_settings` tables and is NOT stored here.
--
-- catalog_models: curated model details per provider (context window, tags,
-- capabilities, pricing, ...). Only a handful of flagship models per provider
-- are seeded by migration 004.

CREATE TABLE IF NOT EXISTS catalog_providers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    adapter TEXT NOT NULL DEFAULT 'openai_compat',
    litellm_prefix TEXT NOT NULL DEFAULT '',
    default_model TEXT NOT NULL DEFAULT '',
    base_url TEXT NOT NULL DEFAULT '',
    api_key_prefix TEXT,
    requires_api_key INTEGER NOT NULL DEFAULT 1,
    swatch_json TEXT NOT NULL DEFAULT '[]',
    capabilities_json TEXT NOT NULL DEFAULT '{}',
    config_fields_json TEXT NOT NULL DEFAULT '[]',
    options_json TEXT NOT NULL DEFAULT '{}',
    is_default_active INTEGER NOT NULL DEFAULT 0,
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS catalog_models (
    provider_id TEXT NOT NULL REFERENCES catalog_providers(id) ON DELETE CASCADE,
    id TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    context_window INTEGER NOT NULL DEFAULT 128000,
    parameters TEXT,
    architecture TEXT,
    input_modalities TEXT NOT NULL DEFAULT '[]',
    output_modalities TEXT NOT NULL DEFAULT '[]',
    tags TEXT NOT NULL DEFAULT '[]',
    model_capabilities_json TEXT NOT NULL DEFAULT '{}',
    speed_tier TEXT,
    best_for TEXT NOT NULL DEFAULT '[]',
    pricing_json TEXT NOT NULL DEFAULT '{}',
    is_default INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (provider_id, id)
);

CREATE INDEX IF NOT EXISTS idx_catalog_models_provider ON catalog_models (provider_id);
