import { describe, expect, it } from 'vitest';
import { appConfig } from '../src/config/appConfig';

describe('appConfig', () => {
  it('resolves a REST backend URL with a trailing slash removed', () => {
    // tests/setup.ts sets VITE_BACKEND_URL=http://localhost:8765
    expect(appConfig.backendUrl).toBe('http://localhost:8765');
    expect(appConfig.backendUrl.endsWith('/')).toBe(false);
  });

  it('buildUrl joins the base URL and path with a single slash', () => {
    expect(appConfig.buildUrl('/startup/validate')).toBe('http://localhost:8765/startup/validate');
    // bare path (no leading slash) is normalized too
    expect(appConfig.buildUrl('startup/validate')).toBe('http://localhost:8765/startup/validate');
  });

  it('buildWsUrl maps http -> ws and appends /ws/test (simulation backend)', () => {
    expect(appConfig.buildWsUrl()).toBe('ws://localhost:8765/ws/test');
  });

  it('exposes timeout and retry defaults', () => {
    expect(appConfig.timeout.fetchMs).toBeGreaterThan(0);
    expect(appConfig.timeout.rpcMs).toBeGreaterThan(0);
    expect(appConfig.ws.maxReconnect).toBeGreaterThanOrEqual(0);
  });
});
