/**
 * Vitest setup — sets ALL required env vars before any test modules are imported.
 *
 * No fallbacks, no defaults. If anything is missing, tests fail immediately.
 */

process.env.ZENITH_ACTIVE_PROVIDER = 'nvidia';
process.env.ZENITH_DB_PATH = ':memory:';
process.env.ZENITH_LOG_LEVEL = 'info';
process.env.ZENITH_MAX_CONTEXT_TOKENS = '128000';
process.env.ZENITH_SUMMARY_THRESHOLD = '0.8';
process.env.ZENITH_BASH_TIMEOUT = '30';
process.env.ZENITH_MAX_ITERATIONS = '25';
process.env.ZENITH_MAX_TOOL_OUTPUT = '10000';
process.env.ZENITH_MAX_RETRIES = '3';
process.env.ZENITH_STREAM_MAX_RETRIES = '2';
process.env.ZENITH_RETRY_BASE_DELAY = '1.0';
process.env.ZENITH_RETRY_MAX_DELAY = '60.0';
process.env.ZENITH_VALIDATION_TIMEOUT = '30';
process.env.ZENITH_STARTUP_RETRIES = '0';
process.env.ZENITH_WEBFETCH_TIMEOUT = '30';
process.env.ZENITH_WEBFETCH_MAX_BYTES = '50000';
process.env.ZENITH_GIT_TIMEOUT = '30';
process.env.ZENITH_MAX_TOKENS = '4096';
process.env.ZENITH_TEMPERATURE = '0.7';
process.env.ZENITH_WS_MAX_RECONNECT = '5';
process.env.ZENITH_WS_RECONNECT_DELAY = '1000';
process.env.ZENITH_WS_RPC_TIMEOUT = '60000';
process.env.ZENITH_GIT_CACHE_TTL = '30000';
process.env.VITE_BACKEND_URL = 'http://localhost:8765';
process.env.VITE_BACKEND_FETCH_TIMEOUT = '5000';
process.env.VITE_DEFAULT_MAX_TOKENS = '4096';
process.env.VITE_DEFAULT_TEMPERATURE = '0.7';
process.env.VITE_FALLBACK_MAX_TOKENS = '30000';
