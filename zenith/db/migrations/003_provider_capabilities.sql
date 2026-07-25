-- Migration 003: Add provider capabilities columns

ALTER TABLE providers ADD COLUMN adapter_type TEXT NOT NULL DEFAULT 'openai_compat';
ALTER TABLE providers ADD COLUMN capabilities_json TEXT NOT NULL DEFAULT '{}';
ALTER TABLE providers ADD COLUMN api_key_prefix TEXT;
