import { describe, expect, it } from 'vitest';
import { ModelService } from '../src/services/providers/ModelService';

describe('ModelService Dynamic DB & Update Operations', () => {
  const service = new ModelService();

  it('loads models for OpenRouter', () => {
    const data = service.getModelsData('openrouter');
    expect(data.provider).toBe('openrouter');
    expect(data.models.length).toBeGreaterThan(0);
    expect(data.models[0].id).toBe('meta-llama/llama-3.3-70b-instruct');
  });

  it('updates models list via updateModelsList()', () => {
    const customModels = [
      { id: 'custom-gpt-5', name: 'Custom GPT-5', contextWindow: 500000 },
    ];
    service.updateModelsList('openai', customModels);

    const updated = service.getModels('openai');
    expect(updated.length).toBe(1);
    expect(updated[0].id).toBe('custom-gpt-5');
    expect(service.getTotalModelsLabel('openai')).toBe('1 models');
  });
});
