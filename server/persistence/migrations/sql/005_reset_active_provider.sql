-- 005: reset stale active-provider state (no default provider concept)
--
-- The application no longer maintains a globally configured "default provider".
-- A provider is active ONLY after the user explicitly selects a model and the
-- setup is saved. This migration clears any stale active-provider state left by
-- older versions while preserving saved credentials (API keys, base URLs,
-- selected models, config) so the setup wizard re-opens on first launch and the
-- user re-activates a provider explicitly.
--
-- Idempotent: safe to run more than once.

-- Mark every provider inactive (retain api_key/base_url/model/config).
UPDATE providers SET is_active = 0;

-- Clear the persisted active-provider marker from app_settings.
DELETE FROM app_settings WHERE key = 'active_provider';
