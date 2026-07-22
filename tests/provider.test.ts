import { describe, expect, it } from 'vitest';
import { PROVIDER_CATALOG } from '../src/modules/providers/ProviderCatalog';
import { ProviderRepository } from '../src/modules/providers/ProviderRepository';
import { ProviderService } from '../src/modules/providers/ProviderService';

describe('Provider Management Module', () => {
  it('loads all 6 supported provider catalogs', () => {
    const keys = Object.keys(PROVIDER_CATALOG);
    expect(keys).toContain('openrouter');
    expect(keys).toContain('openai');
    expect(keys).toContain('anthropic');
    expect(keys).toContain('gemini');
    expect(keys).toContain('groq');
    expect(keys).toContain('custom');
  });

  it('validates provider config API key requirements', () => {
    const repo = new ProviderRepository();
    const service = new ProviderService(repo);

    const openaiValidation = service.validateConfig('openai', { apiKey: '' });
    expect(openaiValidation.valid).toBe(false);
    expect(openaiValidation.error).toContain('API Key is required');

    const validOpenAI = service.validateConfig('openai', { apiKey: 'sk-proj-test12345' });
    expect(validOpenAI.valid).toBe(true);

    const customValidation = service.validateConfig('custom', { baseUrl: 'http://localhost:11434/v1' });
    expect(customValidation.valid).toBe(true);
  });

  it('switches single active provider cleanly', () => {
    const repo = new ProviderRepository();
    const service = new ProviderService(repo);

    service.setActiveProvider('anthropic');
    const active = service.getActiveProvider();

    expect(active.id).toBe('anthropic');
    expect(active.isActive).toBe(true);
    expect(active.meta.name).toBe('Anthropic Claude');
  });

  it('updates provider config settings', () => {
    const repo = new ProviderRepository();
    const service = new ProviderService(repo);

    service.updateConfig('openai', { model: 'o3-mini', apiKey: 'sk-test-key' });
    const state = service.getProviderState('openai');

    expect(state.config.model).toBe('o3-mini');
    expect(state.config.apiKey).toBe('sk-test-key');
  });
});
