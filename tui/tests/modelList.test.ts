import { describe, expect, it } from 'vitest';
import { ModelService } from '../src/services/providers/ModelService';

describe('ModelService Dynamic DB & Update Operations', () => {
  const service = new ModelService();

  it('loads models for OpenRouter', () => {
    const data = service.getModelsData('openrouter');
    expect(data.provider).toBe('openrouter');
    expect(data.models.length).toBeGreaterThan(0);
    expect(data.models[0].id).toBeDefined();
  });

  it('returns correct total models label', () => {
    const label = service.getTotalModelsLabel('openrouter');
    expect(label).toContain('models');
  });
});
