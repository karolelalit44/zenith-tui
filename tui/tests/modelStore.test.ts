import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { ModelStore } from '../src/services/providers/ModelStore';
import type { ModelSelection, ProviderInfo } from '../src/services/providers/types';

let modelFile: string;

function makeStore(): ModelStore {
  process.env.ZENITH_MODEL_FILE = modelFile;
  return new ModelStore();
}

const nvidiaProvider = (overrides: Partial<ProviderInfo> = {}): ProviderInfo => ({
  id: 'nvidia',
  name: 'NVIDIA AI',
  description: '',
  adapter: 'nvidia',
  swatch: [],
  capabilities: {},
  api_key_prefix: null,
  requires_api_key: true,
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
    modelFile = path.join(os.tmpdir(), `zenith-model-test-${Date.now()}-${Math.random()}.json`);
  });

  afterEach(() => {
    if (fs.existsSync(modelFile)) fs.unlinkSync(modelFile);
    if (fs.existsSync(`${modelFile}.tmp`)) fs.unlinkSync(`${modelFile}.tmp`);
    delete process.env.ZENITH_MODEL_FILE;
  });

  it('parses providerID/modelID from a slash string', () => {
    const sel = ModelStore.parse('nvidia/nemotron-3-ultra-550b-a55b');
    expect(sel.providerID).toBe('nvidia');
    expect(sel.modelID).toBe('nemotron-3-ultra-550b-a55b');
    expect(ModelStore.isModelValid('nvidia/nemotron')).toBe(true);
    expect(ModelStore.isModelValid('nvidia/')).toBe(false);
    expect(ModelStore.isModelValid(null)).toBe(false);
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

  it('toggles favorites and persists them', () => {
    const store = makeStore();
    const sel: ModelSelection = { providerID: 'openrouter', modelID: 'claude' };

    expect(store.isFavorite(sel)).toBe(false);
    expect(store.toggleFavorite(sel)).toBe(true);
    expect(store.isFavorite(sel)).toBe(true);
    expect(store.toggleFavorite(sel)).toBe(false);
    expect(store.isFavorite(sel)).toBe(false);
  });

  it('cycles through recent and favorite models', () => {
    const store = makeStore();
    const a: ModelSelection = { providerID: 'nvidia', modelID: 'a' };
    const b: ModelSelection = { providerID: 'nvidia', modelID: 'b' };
    const c: ModelSelection = { providerID: 'nvidia', modelID: 'c' };

    expect(store.cycle()).toBeNull();
    store.set(a);
    store.set(b);
    store.set(c);
    // recent = [c, b, a]; current = c (newest first)
    expect(store.cycle()).toEqual(b);
    expect(store.cycle(true)).toEqual(a);

    // Apply the selection, then cycle relative to the new current.
    store.set(b);
    // recent = [b, c, a]; current = b
    expect(store.cycle()).toEqual(c);
    expect(store.cycle(true)).toEqual(a);

    store.toggleFavorite(a);
    store.toggleFavorite(b);
    store.toggleFavorite(c);
    // favorites = [c, b, a]; current = b (index 1)
    expect(store.cycleFavorite()).toEqual(a);
    expect(store.cycleFavorite(true)).toEqual(c);
  });

  it('reloads state from disk on a new instance', () => {
    const store = makeStore();
    const sel: ModelSelection = { providerID: 'openai', modelID: 'gpt-4o' };
    store.set(sel);
    store.toggleFavorite(sel);

    const reloaded = makeStore();
    expect(reloaded.current).toEqual(sel);
    expect(reloaded.isFavorite(sel)).toBe(true);
  });

  it('resolves the first valid model from the persistence chain', () => {
    const providers = [nvidiaProvider()];
    const store = makeStore();

    // No persisted state -> falls through to the active provider default model.
    expect(store.getFirstValidModel(providers)).toEqual({
      providerID: 'nvidia',
      modelID: 'nemotron-3-ultra-550b-a55b',
    });

    // Persisted current wins when it exists in the provider list.
    const persisted: ModelSelection = { providerID: 'nvidia', modelID: 'nemotron-3-mini-4b' };
    store.set(persisted);
    expect(store.getFirstValidModel(providers)).toEqual(persisted);

    // A stale current (provider not in list) is skipped.
    store.set({ providerID: 'ghost', modelID: 'ghost-model' });
    const resolved = store.getFirstValidModel(providers);
    expect(resolved?.providerID).toBe('nvidia');
    expect(resolved?.modelID).toBe('nemotron-3-ultra-550b-a55b');
  });

  it('formats a selection for display', () => {
    const store = makeStore();
    expect(store.toDisplayString({ providerID: 'nvidia', modelID: 'nemotron' })).toBe('nvidia/nemotron');
    expect(store.toDisplayString(null)).toBe('');
  });
});
