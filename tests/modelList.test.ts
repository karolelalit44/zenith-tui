import { describe, expect, it } from 'vitest';
import { ModelListService } from '../src/modules/providers/ModelListService';

describe('ModelListService Dynamic JSON Loader', () => {
  const service = new ModelListService();

  it('loads models.json for OpenRouter', () => {
    const data = service.getModelsData('openrouter');
    expect(data.provider).toBe('openrouter');
    expect(data.totalModelsLabel).toBe('1200+ models');
    expect(data.models.length).toBeGreaterThan(0);
    expect(data.models[0].id).toBe('openrouter/auto');
  });

  it('loads models.json for OpenAI', () => {
    const models = service.getModels('openai');
    expect(models.some((m) => m.id === 'gpt-4o')).toBe(true);
    expect(models.some((m) => m.id === 'o1')).toBe(true);
  });

  it('loads models.json for Anthropic', () => {
    const label = service.getTotalModelsLabel('anthropic');
    expect(label).toContain('Claude models');
    const contextWindow = service.getContextWindow('anthropic', 'claude-3-5-sonnet-latest');
    expect(contextWindow).toBe(200000);
  });

  it('loads models.json for Gemini, Groq, and Custom', () => {
    expect(service.getModels('gemini').length).toBeGreaterThan(0);
    expect(service.getModels('groq').length).toBeGreaterThan(0);
    expect(service.getModels('custom').length).toBeGreaterThan(0);
  });
});
