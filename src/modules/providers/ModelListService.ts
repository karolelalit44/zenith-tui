import anthropicModels from './anthropic/models.json';
import customModels from './custom/models.json';
import geminiModels from './gemini/models.json';
import groqModels from './groq/models.json';
import openaiModels from './openai/models.json';
import openrouterModels from './openrouter/models.json';
import type { ProviderId } from './types';

export interface ProviderModelItem {
  id: string;
  name: string;
  contextWindow: number;
  description?: string;
}

export interface ProviderModelsData {
  provider: string;
  totalModelsLabel: string;
  models: ProviderModelItem[];
}

const MODEL_DATA_MAP: Record<ProviderId, ProviderModelsData> = {
  openrouter: openrouterModels as ProviderModelsData,
  openai: openaiModels as ProviderModelsData,
  anthropic: anthropicModels as ProviderModelsData,
  gemini: geminiModels as ProviderModelsData,
  groq: groqModels as ProviderModelsData,
  custom: customModels as ProviderModelsData,
};

export class ModelListService {
  public getModelsData(providerId: ProviderId): ProviderModelsData {
    return MODEL_DATA_MAP[providerId] || MODEL_DATA_MAP.openai;
  }

  public getModels(providerId: ProviderId): ProviderModelItem[] {
    return this.getModelsData(providerId).models;
  }

  public getTotalModelsLabel(providerId: ProviderId): string {
    return this.getModelsData(providerId).totalModelsLabel;
  }

  public getContextWindow(providerId: ProviderId, modelId: string): number {
    const models = this.getModels(providerId);
    const found = models.find((m) => m.id === modelId);
    return found ? found.contextWindow : 128000;
  }
}

export const modelListService = new ModelListService();
