import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { modelStore } from '../../services/providers/ModelStore';
import { providerRepository } from '../../services/providers/ProviderRepository';
import { providerService } from '../../services/providers/ProviderService';
import type {
  ModelSelection,
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

type ProviderFlowPhase = 'pick' | 'key' | 'custom' | 'validating' | 'models';

export interface ProviderFlowProps {
  onClose: () => void;
  onComplete?: (sel: ModelSelection) => void;
}

export const ProviderFlow: React.FC<ProviderFlowProps> = ({ onClose, onComplete }) => {
  const [phase, setPhase] = useState<ProviderFlowPhase>('pick');
  const [providers, setProviders] = useState<ProviderState[]>(() => providerService.getAllProviders());
  const [providerID, setProviderID] = useState<ProviderId>(() => providerService.getActiveProviderId());
  const [validateOptions, setValidateOptions] = useState<ValidateProviderOptions>({});
  const [prevPhase, setPrevPhase] = useState<ProviderFlowPhase>('key');

  useEffect(() => {
    providerService.refreshFromBackend().then(() => {
      setProviders(providerService.getAllProviders());
    });
  }, []);

  const provider = useMemo(
    () => providers.find((item) => item.id === providerID) ?? providerService.getProviderState(providerID),
    [providers, providerID],
  );

  const commitModel = useCallback(
    async (sel: ModelSelection) => {
      await providerRepository.setModel(sel.providerID, sel.modelID);
      modelStore.set(sel);
      providerService.notifyChange();
      onComplete?.(sel);
      onClose();
    },
    [onComplete, onClose],
  );

  const handlePick = useCallback((selection: ProviderPickerSelection) => {
    if (selection.type === 'custom') {
      setProviderID('openai_compatible');
      setPhase('custom');
      return;
    }
    const id = selection.providerID!;
    setProviderID(id);
    const state = providerService.getProviderState(id);
    setPhase(state.hasApiKey ? 'models' : 'key');
  }, []);

  const handleKeySubmit = useCallback(
    (values: Record<string, string>) => {
      setPrevPhase('key');
      const targetState = providerService.getProviderState(providerID);
      setValidateOptions({
        apiKey: values.apiKey,
        baseUrl: providerID === 'custom' || providerID === 'openai_compatible' ? values.baseUrl : undefined,
        model: targetState.config.model || targetState.meta.defaultModel,
      });
      setPhase('validating');
    },
    [providerID],
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
      const discovered = result.models ?? [];
      if (discovered.length > 0) {
        setPhase('models');
        return;
      }
      await commitModel({
        providerID,
        modelID: validateOptions.model || provider.meta.defaultModel,
      });
    },
    [providerID, validateOptions.model, provider.meta.defaultModel, commitModel],
  );

  const handleModelSelect = useCallback(
    (sel: ModelSelection) => {
      void commitModel(sel);
    },
    [commitModel],
  );

  switch (phase) {
    case 'pick':
      return (
        <ProviderPicker
          providers={providers}
          connected={providerService.getConnectedIds()}
          onSelect={handlePick}
          onClose={onClose}
        />
      );
    case 'key':
      return <ApiKeyPrompt provider={provider} onBack={() => setPhase('pick')} onSubmit={handleKeySubmit} />;
    case 'custom':
      return <CustomProviderPrompt onBack={() => setPhase('pick')} onSubmit={handleCustomSubmit} />;
    case 'validating':
      return (
        <ValidationProgress
          providerID={providerID}
          providerName={provider.meta.name}
          options={validateOptions}
          onResult={(result) => {
            if (result.valid) void handleValidResult(result);
          }}
          onClose={() => setPhase(prevPhase)}
        />
      );
    case 'models':
      return <ModelPicker providerID={providerID} onSelect={handleModelSelect} onClose={() => setPhase('pick')} />;
  }
};
