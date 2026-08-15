import { describe, expect, it, vi } from 'vitest';
import { appConfig } from '../src/config/appConfig';
import { readDotEnv } from '../src/config/env';

const env = readDotEnv();

const backendBase = env.ZENITH_BACKEND_URL ?? env.VITE_BACKEND_URL ?? 'http://127.0.0.1:8765';
const backendUrl = backendBase.replace(/\/+$/, '');
const wsPath = env.ZENITH_WS_PATH ?? env.VITE_WS_PATH ?? '/ws/test';

describe('appConfig', () => {
  it('resolves the REST backend URL from .env with the trailing slash removed', () => {
    expect(appConfig.backendUrl).toBe(backendUrl);
    expect(appConfig.backendUrl.endsWith('/')).toBe(false);
  });

  it('buildUrl joins the base URL and path with a single slash', () => {
    expect(appConfig.buildUrl('/startup/validate')).toBe(`${backendUrl}/startup/validate`);
    expect(appConfig.buildUrl('startup/validate')).toBe(`${backendUrl}/startup/validate`);
  });

  it('buildWsUrl maps http -> ws and appends the WS path from .env', () => {
    const expected = `${backendUrl.replace(/^http/i, 'ws')}${wsPath.startsWith('/') ? wsPath : `/${wsPath}`}`;
    expect(appConfig.buildWsUrl()).toBe(expected);
  });

  it('buildWsUrl honors ZENITH_WS_PATH so the backend can be swapped by URL alone', async () => {
    vi.stubEnv('ZENITH_WS_PATH', '/ws');
    vi.resetModules();
    const mod = await import('../src/config/appConfig');
    expect(mod.appConfig.buildWsUrl()).toBe(`${backendUrl.replace(/^http/i, 'ws')}/ws`);
    vi.unstubAllEnvs();
  });

  it('exposes positive timeout and retry defaults from .env', () => {
    expect(appConfig.timeout.fetchMs).toBeGreaterThan(0);
    expect(appConfig.timeout.rpcMs).toBeGreaterThan(0);
    expect(appConfig.ws.maxReconnect).toBeGreaterThanOrEqual(0);
  });
});
