import { providerRepository } from './ProviderRepository';
export class ModelService {
    _customCache = {};
    getModelsData(providerId) {
        if (this._customCache[providerId]) {
            return this._customCache[providerId];
        }
        const meta = providerRepository.getProviderMeta(providerId);
        const rawModels = meta.availableModels || [];
        const models = rawModels.map((m) => ({
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
    getModels(providerId) {
        return this.getModelsData(providerId).models;
    }
    getTotalModelsLabel(providerId) {
        return this.getModelsData(providerId).totalModelsLabel;
    }
}
export const modelService = new ModelService();
