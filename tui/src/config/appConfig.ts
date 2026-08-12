import { envInt } from './env';

const BACKEND_BASE = process.env.ZENITH_BACKEND_URL || process.env.VITE_BACKEND_URL || 'http://127.0.0.1:8765';

function parseFloatOrDefault(raw: string | undefined, fallback: number): number {
  if (raw === undefined || raw.trim() === '') return fallback;
  const n = Number.parseFloat(raw.trim());
  return Number.isNaN(n) ? fallback : n;
}

export const appConfig = Object.freeze({
  backendUrl: BACKEND_BASE.replace(/\/+$/, ''),

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

  git: {
    cacheTtlMs: envInt('ZENITH_GIT_CACHE_TTL', 30000),
    timeoutMs: envInt('ZENITH_GIT_TIMEOUT', 30) * 1000,
  },

  startup: {
    connectRetries: envInt('ZENITH_STARTUP_RETRIES', 30),
    initialDelayMs: envInt('ZENITH_STARTUP_RETRY_DELAY_MS', 250),
    maxDelayMs: envInt('ZENITH_STARTUP_RETRY_MAX_DELAY_MS', 1000),
  },

  defaults: {
    temperature: parseFloatOrDefault(process.env.VITE_DEFAULT_TEMPERATURE, 0.7),
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
