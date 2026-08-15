import { envFloat, envInt, envStr } from './env';

const BACKEND_BASE = envStr('ZENITH_BACKEND_URL');
const WS_PATH = envStr('ZENITH_WS_PATH');

export const appConfig = Object.freeze({
  backendUrl: BACKEND_BASE.replace(/\/+$/, ''),

  timeout: {
    fetchMs: envInt('VITE_BACKEND_FETCH_TIMEOUT'),
    rpcMs: envInt('ZENITH_WS_RPC_TIMEOUT'),
  },

  ws: {
    maxReconnect: envInt('ZENITH_WS_MAX_RECONNECT'),
    reconnectDelayMs: envInt('ZENITH_WS_RECONNECT_DELAY'),
    staleTimeoutMs: envInt('ZENITH_WS_STALE_TIMEOUT_MS'),
    reconnectWaitMs: envInt('ZENITH_WS_RECONNECT_WAIT_MS'),
  },

  git: {
    cacheTtlMs: envInt('ZENITH_GIT_CACHE_TTL'),
    timeoutMs: envInt('ZENITH_GIT_TIMEOUT') * 1000,
  },

  startup: {
    connectRetries: envInt('ZENITH_STARTUP_RETRIES'),
    initialDelayMs: envInt('ZENITH_STARTUP_RETRY_DELAY_MS'),
    maxDelayMs: envInt('ZENITH_STARTUP_RETRY_MAX_DELAY_MS'),
  },

  defaults: {
    temperature: envFloat('VITE_DEFAULT_TEMPERATURE'),
    fallbackMaxTokens: envInt('VITE_FALLBACK_MAX_TOKENS'),
  },

  buildUrl(path: string): string {
    return `${BACKEND_BASE.replace(/\/+$/, '')}${path.startsWith('/') ? path : `/${path}`}`;
  },

  buildWsUrl(): string {
    const base = BACKEND_BASE.replace(/\/+$/, '');
    const ws = base.replace(/^http:/i, 'ws:').replace(/^https:/i, 'wss:');
    const path = WS_PATH.startsWith('/') ? WS_PATH : `/${WS_PATH}`;
    return `${ws}${path}`;
  },
});

export type AppConfig = typeof appConfig;
