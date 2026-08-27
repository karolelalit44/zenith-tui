import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { providerRepository } from '../../services/providers/ProviderRepository';
import { providerService } from '../../services/providers/ProviderService';
import type {
  ModelSelection,
  ProviderCatalogItem,
  ProviderId,
  ProviderState,
  ValidateProviderOptions,
  ValidationResult,
} from '../../services/providers/types';
import { ApiKeyPrompt } from './ApiKeyPrompt';
import { CustomProviderPrompt } from './CustomProviderPrompt';
import { ModelPicker } from './ModelPicker';
import { ProviderPicker, type ProviderPickerSelection } from './ProviderPicker';
import { ValidationProgress } from './ValidationProgress';

/**
 * Default-provider flow:
 *   Choose Provider → Choose Model → Enter API Key → Validate → Mark active.
 * Custom providers use their own dedicated form (see handleCustomSubmit).
 */
type ProviderFlowPhase = 'pick' | 'models' | 'key' | 'custom' | 'validating';

export interface ProviderFlowProps {
  onClose: () => void;
  onComplete?: (sel: ModelSelection) => void;
  initialProviderID?: ProviderId;
}

export const ProviderFlow: React.FC<ProviderFlowProps> = ({ onClose, onComplete, initialProviderID }) => {
  const [phase, setPhase] = useState<ProviderFlowPhase>(initialProviderID ? 'models' : 'pick');
  const [catalogItems, setCatalogItems] = useState<ProviderCatalogItem[]>([]);
  const [providers, setProviders] = useState<ProviderState[]>([]);
  const [providerID, setProviderID] = useState<ProviderId>(initialProviderID ?? '');
  const [selectedModel, setSelectedModel] = useState<string | null>(null);
  const [validateOptions, setValidateOptions] = useState<ValidateProviderOptions>({});
  const [prevPhase, setPrevPhase] = useState<ProviderFlowPhase>('pick');

  useEffect(() => {
    providerService.refreshFromBackend().then(() => setProviders(providerService.getAllProviders()));
    providerRepository.fetchProviderCatalog().then(setCatalogItems);
  }, []);

  const provider = useMemo<ProviderState>(() => {
    return providers.find((item) => item.id === providerID) ?? providerService.getProviderState(providerID);
  }, [providers, providerID]);

  const commitModel = useCallback(
    async (sel: ModelSelection) => {
      await providerRepository.setModel(sel.providerID, sel.modelID);
      providerService.notifyChange();
      onComplete?.(sel);
      onClose();
    },
    [onComplete, onClose],
  );

  const handlePick = useCallback((selection: ProviderPickerSelection) => {
    setProviderID(selection.providerID ?? '');
    setSelectedModel(null);
    setPhase(selection.type === 'custom' ? 'custom' : 'models');
  }, []);

  const handleModelSelect = useCallback((sel: ModelSelection) => {
    setProviderID(sel.providerID);
    setSelectedModel(sel.modelID);
    setPhase('key');
  }, []);

  const handleKeySubmit = useCallback(
    (values: Record<string, string>) => {
      setPrevPhase('key');
      setValidateOptions({
        apiKey: values.apiKey,
        model: selectedModel ?? provider.meta.defaultModel ?? '',
      });
      setPhase('validating');
    },
    [selectedModel, provider],
  );

  const handleCustomSubmit = useCallback((values: Record<string, string>) => {
    setPrevPhase('custom');
    setValidateOptions({
      name: values.name || 'Custom Provider',
      baseUrl: values.baseUrl,
      apiKey: values.apiKey || undefined,
      model: values.model || undefined,
    });
    setPhase('validating');
  }, []);

  const handleValidResult = useCallback(
    async (result: ValidationResult) => {
      await providerService.refreshFromBackend();
      setProviders(providerService.getAllProviders());
      const resolvedModel =
        selectedModel || validateOptions.model || result.models?.[0]?.id || provider.meta.defaultModel || '';
      if (!resolvedModel) return;
      await commitModel({ providerID: providerID || provider.meta.id, modelID: resolvedModel });
    },
    [providerID, selectedModel, validateOptions.model, provider, commitModel],
  );

  switch (phase) {
    case 'pick':
      return <ProviderPicker providers={catalogItems} onSelect={handlePick} onClose={onClose} />;
    case 'models':
      return <ModelPicker provider={provider} onSelect={handleModelSelect} onClose={() => setPhase('pick')} />;
    case 'key':
      return (
        <ApiKeyPrompt
          provider={{ ...provider, meta: { ...provider.meta, name: provider.meta.name || providerID } }}
          onBack={() => setPhase('models')}
          onSubmit={handleKeySubmit}
        />
      );
    case 'custom':
      return <CustomProviderPrompt onBack={() => setPhase('pick')} onSubmit={handleCustomSubmit} />;
    case 'validating':
      return (
        <ValidationProgress
          providerID={providerID || provider.meta.id}
          providerName={provider.meta.name || providerID}
          options={validateOptions}
          onResult={(result) => {
            if (result.valid) void handleValidResult(result);
          }}
          onClose={() => setPhase(prevPhase)}
        />
      );
    default:
      return null;
  }
};
