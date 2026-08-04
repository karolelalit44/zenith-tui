/**
 * Centralized environment configuration for the Zenith TUI frontend.
 *
 * Single source of truth for every environment setting the app cares about:
 * backend URL (REST + WebSocket), environment / development status, fetch &
 * RPC timeouts, WebSocket reconnect policy, startup retry policy, and provider
 * defaults. Services read their settings from here instead of scattering
 * `process.env` lookups (and copying backendUrl helpers) across the codebase.
 *
 * Low-level, fallback-free getters live in `./env.ts`; this module composes
 * them into one typed, immutable object with safe defaults for optional values.
 */

import { envInt } from './env';

/** Resolved REST backend base URL. */
const BACKEND_BASE = process.env.ZENITH_BACKEND_URL || process.env.VITE_BACKEND_URL || 'http://127.0.0.1:8765';

function resolveEnvironment(): 'development' | 'production' {
  const env = (process.env.NODE_ENV || process.env.ZENITH_ENV || '').toLowerCase();
  if (env === 'production' || env === 'prod') return 'production';
  return 'development';
}

function parseFloatOrDefault(raw: string | undefined, fallback: number): number {
  if (raw === undefined || raw.trim() === '') return fallback;
  const n = Number.parseFloat(raw.trim());
  return Number.isNaN(n) ? fallback : n;
}

const environment = resolveEnvironment();

export const appConfig = Object.freeze({
  /** Environment name ('development' | 'production'). */
  environment,
  /** True when running in a non-production environment. */
  isDevelopment: environment !== 'production',
  /** REST backend base URL with any trailing slash removed. */
  backendUrl: BACKEND_BASE.replace(/\/+$/, ''),
  /** Backend server host / port (reference for diagnostics). */
  host: process.env.ZENITH_HOST || 'localhost',
  port: envInt('ZENITH_PORT', 8765),

  timeout: {
    /** REST fetch timeout in milliseconds. */
    fetchMs: (() => {
      const raw = envInt('VITE_BACKEND_FETCH_TIMEOUT', 10000);
      return raw <= 0 ? 10000 : raw;
    })(),
    /** WebSocket JSON-RPC timeout in milliseconds. */
    rpcMs: envInt('ZENITH_WS_RPC_TIMEOUT', 60000),
  },

  ws: {
    maxReconnect: envInt('ZENITH_WS_MAX_RECONNECT', 5),
    reconnectDelayMs: envInt('ZENITH_WS_RECONNECT_DELAY', 1000),
  },

  startup: {
    connectRetries: envInt('ZENITH_STARTUP_RETRIES', 30),
    initialDelayMs: envInt('ZENITH_STARTUP_RETRY_DELAY_MS', 250),
    maxDelayMs: envInt('ZENITH_STARTUP_RETRY_MAX_DELAY_MS', 1000),
  },

  defaults: {
    temperature: parseFloatOrDefault(process.env.VITE_DEFAULT_TEMPERATURE, 0.7),
    maxTokens: envInt('VITE_DEFAULT_MAX_TOKENS', 4096),
    fallbackMaxTokens: envInt('VITE_FALLBACK_MAX_TOKENS', 4096),
  },

  /**
   * Join the REST base URL with an API path, collapsing any trailing slash
   * on the base and normalizing the leading slash on the path.
   */
  buildUrl(path: string): string {
    return `${BACKEND_BASE.replace(/\/+$/, '')}${path.startsWith('/') ? path : `/${path}`}`;
  },

  /**
   * Derive the WebSocket URL from the backend HTTP base — maps http(s) to
   * ws(s) and appends `/ws` unless it is already present.
   */
  buildWsUrl(): string {
    const base = BACKEND_BASE.replace(/\/+$/, '');
    const ws = base.replace(/^http:/i, 'ws:').replace(/^https:/i, 'wss:');
    return /\/ws$/.test(ws) ? ws : `${ws}/ws`;
  },
});

export type AppConfig = typeof appConfig;
