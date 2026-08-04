import { describe, expect, it, vi } from 'vitest';
import { StartupService } from '../src/services/api/StartupService';

const READY_RESPONSE = {
  status: 'ready',
  missing: [],
  active_provider: 'openai',
  active_model: 'gpt-4o',
  provider_count: 1,
  message: '',
};

const CONFIG_REQUIRED_RESPONSE = {
  status: 'configuration_required',
  missing: ['provider', 'apiKey'],
  active_provider: '',
  active_model: '',
  provider_count: 0,
  message: 'Missing configuration: provider, apiKey',
};

describe('StartupService Backend Validation', () => {
  it('returns ready when backend validates successfully', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(READY_RESPONSE),
    });

    const svc = new StartupService();
    const state = await svc.initialize();

    expect(state.phase).toBe('ready');
    expect(state.result?.status).toBe('ready');
    expect(state.result?.active_provider).toBe('openai');
    expect(state.result?.active_model).toBe('gpt-4o');
    expect(state.error).toBeNull();

    vi.restoreAllMocks();
  });

  it('returns setup phase when configuration is missing', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(CONFIG_REQUIRED_RESPONSE),
    });

    const svc = new StartupService();
    const state = await svc.initialize();

    expect(state.phase).toBe('setup');
    expect(state.result?.status).toBe('configuration_required');
    expect(state.result?.missing).toContain('provider');
    expect(state.result?.missing).toContain('apiKey');
    expect(state.error).toBeNull();

    vi.restoreAllMocks();
  });

  it('returns error phase when backend is unreachable', async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error('fetch failed'));

    const svc = new StartupService();
    const state = await svc.initialize();

    expect(state.phase).toBe('error');
    expect(state.result).toBeNull();
    expect(state.error).toBeTruthy();

    vi.restoreAllMocks();
  });
});
