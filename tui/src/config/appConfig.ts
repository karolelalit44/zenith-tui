import {
  ZENITH_BACKEND_FETCH_TIMEOUT,
  ZENITH_BACKEND_URL,
  ZENITH_DEFAULT_TEMPERATURE,
  ZENITH_FALLBACK_MAX_TOKENS,
  ZENITH_GIT_CACHE_TTL,
  ZENITH_GIT_TIMEOUT,
  ZENITH_STARTUP_RETRIES,
  ZENITH_STARTUP_RETRY_DELAY_MS,
  ZENITH_STARTUP_RETRY_MAX_DELAY_MS,
  ZENITH_WS_MAX_RECONNECT,
  ZENITH_WS_PATH,
  ZENITH_WS_RECONNECT_DELAY,
  ZENITH_WS_RECONNECT_WAIT_MS,
  ZENITH_WS_RPC_TIMEOUT,
  ZENITH_WS_STALE_TIMEOUT_MS,
} from './environment';

const BACKEND_BASE = ZENITH_BACKEND_URL;
const WS_PATH = ZENITH_WS_PATH;

export const appConfig = Object.freeze({
  backendUrl: BACKEND_BASE.replace(/\/+$/, ''),

  timeout: {
    fetchMs: ZENITH_BACKEND_FETCH_TIMEOUT,
    rpcMs: ZENITH_WS_RPC_TIMEOUT,
  },

  ws: {
    maxReconnect: ZENITH_WS_MAX_RECONNECT,
    reconnectDelayMs: ZENITH_WS_RECONNECT_DELAY,
    staleTimeoutMs: ZENITH_WS_STALE_TIMEOUT_MS,
    reconnectWaitMs: ZENITH_WS_RECONNECT_WAIT_MS,
  },

  git: {
    cacheTtlMs: ZENITH_GIT_CACHE_TTL,
    timeoutMs: ZENITH_GIT_TIMEOUT * 1000,
  },

  startup: {
    connectRetries: ZENITH_STARTUP_RETRIES,
    initialDelayMs: ZENITH_STARTUP_RETRY_DELAY_MS,
    maxDelayMs: ZENITH_STARTUP_RETRY_MAX_DELAY_MS,
  },

  defaults: {
    temperature: ZENITH_DEFAULT_TEMPERATURE,
    fallbackMaxTokens: ZENITH_FALLBACK_MAX_TOKENS,
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
