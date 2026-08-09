-- 007: provider rate-limit metadata
--
-- Adds a per-provider `rate_limit` hint used by the client-side request
-- throttle (llm_provider._RequestThrottle). Google AI Studio free tier allows
-- ~15 requests/min, so a ~4 s minimum interval between request starts keeps a
-- long turn from exhausting the quota (see todo/02-rate-limiting-quota-handling.md).
--
-- Idempotent: plain ADD COLUMN (same convention as 002/004); the UPDATE only
-- touches the google row so other providers keep the empty '{}' default.

ALTER TABLE catalog_providers ADD COLUMN rate_limit_json TEXT NOT NULL DEFAULT '{}';

UPDATE catalog_providers SET rate_limit_json = '{"requests_per_minute": 15}' WHERE id = 'google';
