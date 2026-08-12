import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ProviderRepository } from '../src/services/providers/ProviderRepository';
import { ProviderService } from '../src/services/providers/ProviderService';
import type { ProviderInfo, ProviderListResponse, ProviderModelInfo } from '../src/services/providers/types';

function provider(overrides: Partial<ProviderInfo>): ProviderInfo {
  return {
    id: 'p',
    name: 'P',
    description: '',
    config_fields: [],
    options: {},
    has_api_key: false,
    api_key_masked: '',
    validation_status: 'unconfigured',
    last_validation_error: '',
    is_active: false,
    model: '',
    models: {},
    ...overrides,
  };
}

function model(id: string, name: string, isDefault: boolean): ProviderModelInfo {
  return { id, name, context_window: 128000, description: '', is_default: isDefault };
}

/** Backend-equivalent payload (SQL-backed `/startup/providers`). */
const LIST: ProviderListResponse = {
  all: [
    provider({
      id: 'openrouter',
      name: 'OpenRouter',
      model: 'openrouter/free',
      models: { 'openrouter/free': model('openrouter/free', 'Free Models Router', true) },
    }),
    provider({
      id: 'openai',
      name: 'OpenAI',
      model: 'gpt-4o-mini',
      models: {
        'gpt-4o-mini': model('gpt-4o-mini', 'GPT-4o Mini', true),
        'o3-mini': model('o3-mini', 'o3-mini', false),
      },
    }),
    provider({ id: 'anthropic', name: 'Anthropic', model: 'claude-sonnet-4-20250514' }),
    provider({ id: 'google', name: 'Google AI Studio', model: 'gemini-3.5-flash-lite' }),
    provider({ id: 'groq', name: 'Groq', model: 'llama-3.3-70b-versatile' }),
    provider({ id: 'nvidia', name: 'NVIDIA AI', model: 'nvidia/nemotron-3-ultra-550b-a55b', is_active: true }),
    provider({ id: 'custom', name: 'Custom OpenAI-Compatible', model: 'llama3', custom_flow: true }),
  ],
  active: 'nvidia',
  connected: [],
};

async function makeRepo(): Promise<ProviderRepository> {
  const repo = new ProviderRepository();
  await repo.fetchProviderList();
  return repo;
}

describe('Provider Management Module', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(JSON.stringify(LIST), { status: 200 })),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('loads provider metadata from the backend payload', async () => {
    const repo = await makeRepo();
    expect(repo.getProviderMeta('openrouter')?.name).toBe('OpenRouter');
    expect(repo.getProviderMeta('openai')?.name).toBe('OpenAI');
    expect(repo.getProviderMeta('anthropic')?.name).toBe('Anthropic');
    expect(repo.getProviderMeta('google')?.name).toBe('Google AI Studio');
    expect(repo.getProviderMeta('groq')?.name).toBe('Groq');
    expect(repo.getProviderMeta('nvidia')?.name).toBe('NVIDIA AI');
    expect(repo.getProviderMeta('custom')?.name).toBe('Custom OpenAI-Compatible');
    expect(repo.getProviderMeta('ghost')).toBeUndefined();
  });

  it('validates provider config API key requirements', async () => {
    const repo = await makeRepo();
    const service = new ProviderService(repo);

    const openaiValidation = service.validateConfig('openai', { apiKey: '' });
    expect(openaiValidation.valid).toBe(false);
    expect(openaiValidation.error).toContain('API Key is required');

    const validOpenAI = service.validateConfig('openai', { apiKey: 'sk-proj-test12345' });
    expect(validOpenAI.valid).toBe(true);

    const customValidation = service.validateConfig('custom', { baseUrl: 'http://localhost:11434/v1' });
    expect(customValidation.valid).toBe(true);
  });

  it('defaults to the backend active provider before any local selection', async () => {
    const repo = await makeRepo();
    const service = new ProviderService(repo);

    expect(service.getActiveProviderId()).toBe('nvidia');
    expect(service.getAllProviders().map((p) => p.id)).toEqual([
      'openrouter',
      'openai',
      'anthropic',
      'google',
      'groq',
      'nvidia',
      'custom',
    ]);
  });
});
