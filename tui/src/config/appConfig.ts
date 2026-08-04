import { envInt } from './env';

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
  environment,

  isDevelopment: environment !== 'production',

  backendUrl: BACKEND_BASE.replace(/\/+$/, ''),
  /** Backend server host / port (reference for diagnostics). */
  host: process.env.ZENITH_HOST || 'localhost',
  port: envInt('ZENITH_PORT', 8765),

  timeout: {
    fetchMs: (() => {
      const raw = envInt('VITE_BACKEND_FETCH_TIMEOUT', 10000);
      return raw <= 0 ? 10000 : raw;
    })(),

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

  buildUrl(path: string): string {
    return `${BACKEND_BASE.replace(/\/+$/, '')}${path.startsWith('/') ? path : `/${path}`}`;
  },

  buildWsUrl(): string {
    const base = BACKEND_BASE.replace(/\/+$/, '');
    const ws = base.replace(/^http:/i, 'ws:').replace(/^https:/i, 'wss:');
    return /\/ws$/.test(ws) ? ws : `${ws}/ws`;
  },
});

export type AppConfig = typeof appConfig;
