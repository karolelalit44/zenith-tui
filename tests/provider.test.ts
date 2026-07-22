import { describe, expect, it } from 'vitest';
import { ProviderRepository } from '../src/services/providers/ProviderRepository';
import { ProviderService } from '../src/services/providers/ProviderService';

describe('Provider Management Module', () => {
  it('loads all 6 supported provider metadata configs from JSON', () => {
    const repo = new ProviderRepository();
    expect(repo.getProviderMeta('openrouter').name).toBe('OpenRouter AI');
    expect(repo.getProviderMeta('openai').name).toBe('OpenAI Direct');
    expect(repo.getProviderMeta('anthropic').name).toBe('Anthropic Claude');
    expect(repo.getProviderMeta('gemini').name).toBe('Google Gemini');
    expect(repo.getProviderMeta('groq').name).toBe('Groq LPU Acceleration');
    expect(repo.getProviderMeta('custom').name).toBe('Custom Endpoint (Ollama / vLLM / Local)');
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
