import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ModelStore } from '../src/services/providers/ModelStore';
import type { ModelSelection, ProviderInfo } from '../src/services/providers/types';

function makeStore(): ModelStore {
  return new ModelStore();
}

const nvidiaProvider = (overrides: Partial<ProviderInfo> = {}): ProviderInfo => ({
  id: 'nvidia',
  name: 'NVIDIA AI',
  description: '',
  config_fields: [],
  options: {},
  has_api_key: true,
  api_key_masked: 'sk-…masked',
  validation_status: 'validated',
  last_validation_error: '',
  is_active: true,
  model: 'nemotron-3-ultra-550b-a55b',
  models: {
    'nemotron-3-ultra-550b-a55b': {
      id: 'nemotron-3-ultra-550b-a55b',
      name: 'Nemotron Ultra 550B',
      context_window: 131072,
      description: '',
      is_default: true,
    },
    'nemotron-3-mini-4b': {
      id: 'nemotron-3-mini-4b',
      name: 'Nemotron Mini 4B',
      context_window: 65536,
      description: '',
      is_default: false,
    },
  },
  ...overrides,
});

describe('ModelStore', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(JSON.stringify({ current: null, recent: [], favorite: [] }), { status: 200 })),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('sets current model and pushes to recents (newest first, capped at 10)', () => {
    const store = makeStore();
    const a: ModelSelection = { providerID: 'nvidia', modelID: 'a' };
    const b: ModelSelection = { providerID: 'nvidia', modelID: 'b' };

    store.set(a);
    expect(store.current).toEqual(a);

    store.set(b);
    store.set(a);
    expect(store.recent).toHaveLength(2);
    expect(store.recent[0]).toEqual(a);
    expect(store.recent[1]).toEqual(b);

    for (let i = 0; i < 12; i++) {
      store.set({ providerID: 'nvidia', modelID: `m${i}` });
    }
    expect(store.recent).toHaveLength(10);
  });

  it('toggles favorites', () => {
    const store = makeStore();
    const sel: ModelSelection = { providerID: 'openrouter', modelID: 'claude' };

    expect(store.isFavorite(sel)).toBe(false);
    expect(store.toggleFavorite(sel)).toBe(true);
    expect(store.isFavorite(sel)).toBe(true);
    expect(store.toggleFavorite(sel)).toBe(false);
    expect(store.isFavorite(sel)).toBe(false);
  });

  it('hydrates current/recent/favorite from the backend SQL store', async () => {
    const store = makeStore();
    const sel: ModelSelection = { providerID: 'openai', modelID: 'gpt-4o' };
    const other: ModelSelection = { providerID: 'openai', modelID: 'gpt-4o-mini' };
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response(JSON.stringify({ current: sel, recent: [sel, other], favorite: [sel] }), { status: 200 }),
      ),
    );

    await store.hydrate();

    expect(store.current).toEqual(sel);
    expect(store.recent).toEqual([sel, other]);
    expect(store.isFavorite(sel)).toBe(true);
  });

  it('only resolves explicitly selected models (no default provider/model fallback)', () => {
    const providers = [nvidiaProvider()];
    const store = makeStore();

    // No persisted selection -> null (never falls back to a default provider/model).
    expect(store.getFirstValidModel(providers)).toBeNull();

    // Persisted current wins when it exists in the provider list.
    const persisted: ModelSelection = { providerID: 'nvidia', modelID: 'nemotron-3-mini-4b' };
    store.set(persisted);
    expect(store.getFirstValidModel(providers)).toEqual(persisted);

    // A stale current (provider not in list) is skipped, falling back to recents.
    store.set({ providerID: 'ghost', modelID: 'ghost-model' });
    const resolved = store.getFirstValidModel(providers);
    expect(resolved).toEqual(persisted);
  });

  it('formats a selection for display', () => {
    const store = makeStore();
    expect(store.toDisplayString({ providerID: 'nvidia', modelID: 'nemotron' })).toBe('nvidia/nemotron');
    expect(store.toDisplayString(null)).toBe('');
  });

  it('does not duplicate the provider prefix when the model id is already qualified', () => {
    const store = makeStore();
    expect(store.toDisplayString({ providerID: 'nvidia', modelID: 'nvidia/nemotron-3-ultra-550b-a55b' })).toBe(
      'nvidia/nemotron-3-ultra-550b-a55b',
    );
  });
});
