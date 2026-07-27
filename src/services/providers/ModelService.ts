import { providerRepository } from './ProviderRepository';
import type { ProviderId } from './types';

interface ProviderModelItem {
  id: string;
  name: string;
  contextWindow: number;
  description?: string;
}

interface ProviderModelsData {
  provider: string;
  totalModelsLabel: string;
  models: ProviderModelItem[];
}

export class ModelService {
  private _customCache: Partial<Record<ProviderId, ProviderModelsData>> = {};

  public getModelsData(providerId: ProviderId): ProviderModelsData {
    if (this._customCache[providerId]) {
      return this._customCache[providerId]!;
    }
    const meta = providerRepository.getProviderMeta(providerId);
    const rawModels = meta.availableModels || [];
    const models: ProviderModelItem[] = rawModels.map((m) => ({
      id: m.id,
      name: m.name,
      contextWindow: 128000,
      description: m.description,
    }));

    return {
      provider: providerId,
      totalModelsLabel: `${models.length} models`,
      models,
    };
  }

  public getModels(providerId: ProviderId): ProviderModelItem[] {
    return this.getModelsData(providerId).models;
  }

  public getTotalModelsLabel(providerId: ProviderId): string {
    return this.getModelsData(providerId).totalModelsLabel;
  }
}

export const modelService = new ModelService();
