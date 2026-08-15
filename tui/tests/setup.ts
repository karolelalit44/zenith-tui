/**
 * Vitest setup. Frontend config values come from `tui/.env` (the source of
 * truth, loaded by src/config/env.ts); this file only pins server-mirror and
 * test-scoped values that have no `.env` home.
 */

process.env.ZENITH_DB_PATH = ':memory:';
process.env.ZENITH_LOG_LEVEL = 'info';
process.env.ZENITH_MAX_CONTEXT_TOKENS = '128000';
process.env.ZENITH_SUMMARY_THRESHOLD = '0.8';
process.env.ZENITH_BASH_TIMEOUT = '30';
process.env.ZENITH_MAX_TOOL_OUTPUT = '10000';
process.env.ZENITH_VALIDATION_TIMEOUT = '30';
// Fail fast on unreachable backends instead of retrying for ~30s in tests.
process.env.ZENITH_STARTUP_RETRIES = '0';
process.env.ZENITH_WEBFETCH_TIMEOUT = '30';
process.env.ZENITH_WEBFETCH_MAX_BYTES = '50000';
process.env.ZENITH_MAX_TOKENS = '4096';
process.env.ZENITH_TEMPERATURE = '0.7';
