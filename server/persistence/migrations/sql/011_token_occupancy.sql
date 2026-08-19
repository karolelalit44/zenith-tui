-- QA-10: token telemetry honesty.
-- Distinguish provider-billed usage (total_tokens and friends) from composed
-- context occupancy. Older rows default to 0 (occupancy unknown); consumers
-- fall back to total_tokens when occupancy is absent.
ALTER TABLE token_usage ADD COLUMN context_occupancy INTEGER NOT NULL DEFAULT 0;