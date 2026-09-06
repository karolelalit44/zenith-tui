/**
 * Environment configuration for Zenith TUI.
 *
 * Central source of truth for runtime environment details and configuration.
 * No .env files are loaded; environment configuration details are defined directly
 * as constant variables in this module.
 */

// Direct constant values for environment configuration
export const ZENITH_BACKEND_URL: string = process.env.ZENITH_BACKEND_URL || 'http://127.0.0.1:8765';
export const ZENITH_WS_PATH: string = process.env.ZENITH_WS_PATH || '/ws';
export const ZENITH_BACKEND_FETCH_TIMEOUT: number = Number(process.env.ZENITH_BACKEND_FETCH_TIMEOUT || 10000);
export const VITE_BACKEND_FETCH_TIMEOUT: number = ZENITH_BACKEND_FETCH_TIMEOUT;
export const ZENITH_WS_RPC_TIMEOUT: number = Number(process.env.ZENITH_WS_RPC_TIMEOUT || 60000);
export const ZENITH_WS_MAX_RECONNECT: number = Number(process.env.ZENITH_WS_MAX_RECONNECT || 5);
export const ZENITH_WS_RECONNECT_DELAY: number = Number(process.env.ZENITH_WS_RECONNECT_DELAY || 1000);
export const ZENITH_WS_STALE_TIMEOUT_MS: number = Number(process.env.ZENITH_WS_STALE_TIMEOUT_MS || 600000);
export const ZENITH_WS_RECONNECT_WAIT_MS: number = Number(process.env.ZENITH_WS_RECONNECT_WAIT_MS || 20000);
export const ZENITH_GIT_CACHE_TTL: number = Number(process.env.ZENITH_GIT_CACHE_TTL || 30000);
export const ZENITH_GIT_TIMEOUT: number = Number(process.env.ZENITH_GIT_TIMEOUT || 30);
export const ZENITH_STARTUP_RETRIES: number = Number(process.env.ZENITH_STARTUP_RETRIES || 30);
export const ZENITH_STARTUP_RETRY_DELAY_MS: number = Number(process.env.ZENITH_STARTUP_RETRY_DELAY_MS || 250);
export const ZENITH_STARTUP_RETRY_MAX_DELAY_MS: number = Number(process.env.ZENITH_STARTUP_RETRY_MAX_DELAY_MS || 1000);
export const ZENITH_DEFAULT_TEMPERATURE: number = Number(process.env.ZENITH_DEFAULT_TEMPERATURE || 0.7);
export const VITE_DEFAULT_TEMPERATURE: number = ZENITH_DEFAULT_TEMPERATURE;
export const ZENITH_FALLBACK_MAX_TOKENS: number = Number(process.env.ZENITH_FALLBACK_MAX_TOKENS || 4096);
export const VITE_FALLBACK_MAX_TOKENS: number = ZENITH_FALLBACK_MAX_TOKENS;
export const ZENITH_CONTEXT_ATTENTION: number = Number(process.env.ZENITH_CONTEXT_ATTENTION || 0.7);
export const ZENITH_CONTEXT_PREPARING: number = Number(process.env.ZENITH_CONTEXT_PREPARING || 0.85);
export const ZENITH_CONTEXT_REQUIRED: number = Number(process.env.ZENITH_CONTEXT_REQUIRED || 0.95);

const _ALL_CONSTANTS: Record<string, string | number> = {
  ZENITH_BACKEND_URL,
  ZENITH_WS_PATH,
  ZENITH_BACKEND_FETCH_TIMEOUT,
  VITE_BACKEND_FETCH_TIMEOUT,
  ZENITH_WS_RPC_TIMEOUT,
  ZENITH_WS_MAX_RECONNECT,
  ZENITH_WS_RECONNECT_DELAY,
  ZENITH_WS_STALE_TIMEOUT_MS,
  ZENITH_WS_RECONNECT_WAIT_MS,
  ZENITH_GIT_CACHE_TTL,
  ZENITH_GIT_TIMEOUT,
  ZENITH_STARTUP_RETRIES,
  ZENITH_STARTUP_RETRY_DELAY_MS,
  ZENITH_STARTUP_RETRY_MAX_DELAY_MS,
  ZENITH_DEFAULT_TEMPERATURE,
  VITE_DEFAULT_TEMPERATURE,
  ZENITH_FALLBACK_MAX_TOKENS,
  VITE_FALLBACK_MAX_TOKENS,
  ZENITH_CONTEXT_ATTENTION,
  ZENITH_CONTEXT_PREPARING,
  ZENITH_CONTEXT_REQUIRED,
};

// Seed process.env with configuration values for any unset keys
for (const [key, val] of Object.entries(_ALL_CONSTANTS)) {
  if (process.env[key] === undefined) {
    process.env[key] = String(val);
  }
}

export function envStr(key: string, _defaultValue?: string): string {
  const val = process.env[key];
  if (val !== undefined && val.trim() !== '') {
    return val.trim();
  }
  const directVal = _ALL_CONSTANTS[key];
  if (directVal !== undefined) {
    return String(directVal);
  }
  throw new Error(`Required environment variable '${key}' is not defined in environment configuration.`);
}

export function envInt(key: string, _defaultValue?: number): number {
  const raw = envStr(key);
  const n = Number(raw);
  if (!Number.isNaN(n)) return n;
  throw new Error(`Environment variable '${key}' must be a valid number.`);
}

export function envFloat(key: string, _defaultValue?: number): number {
  const raw = envStr(key);
  const n = Number.parseFloat(raw);
  if (!Number.isNaN(n)) return n;
  throw new Error(`Environment variable '${key}' must be a valid number.`);
}

export function envBool(key: string, _defaultValue?: boolean): boolean {
  const raw = envStr(key).toLowerCase();
  if (raw === '1' || raw === 'true' || raw === 'yes' || raw === 'on') return true;
  if (raw === '0' || raw === 'false' || raw === 'no' || raw === 'off') return false;
  throw new Error(`Environment variable '${key}' must be a valid boolean.`);
}

export const getEnv = envStr;
export const getInt = envInt;
export const getFloat = envFloat;
export const getBool = envBool;

export function readEnvironment(): Record<string, string> {
  const result: Record<string, string> = {};
  for (const [key, val] of Object.entries(_ALL_CONSTANTS)) {
    result[key] = String(val);
  }
  for (const [key, val] of Object.entries(process.env)) {
    if (val !== undefined) {
      result[key] = val;
    }
  }
  return result;
}
