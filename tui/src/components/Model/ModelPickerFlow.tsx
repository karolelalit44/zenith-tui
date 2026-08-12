import React, { useState } from 'react';
import { ModelPicker } from '../../screens/Provider/ModelPicker';
import { ProviderFlow } from '../../screens/Provider/ProviderFlow';
import { modelStore } from '../../services/providers/ModelStore';
import { providerRepository } from '../../services/providers/ProviderRepository';
import { providerService } from '../../services/providers/ProviderService';
import type { ModelSelection, ProviderId } from '../../services/providers/types';
import { RoundedBox } from '../ui/RoundedBox';

interface ModelPickerFlowProps {
  onClose: () => void;
  onOpenProvider?: () => void;
}

const isConfigured = (providerID: string): boolean => {
  const info = providerRepository.getProviderInfo(providerID);
  return Boolean(info && (info.has_api_key || info.validation_status === 'validated' || info.is_active));
};

export const ModelPickerFlow: React.FC<ModelPickerFlowProps> = ({ onClose, onOpenProvider }) => {
  const [configProvider, setConfigProvider] = useState<ProviderId | null>(null);

  const commit = (sel: ModelSelection) => {
    void providerRepository.setModel(sel.providerID, sel.modelID).then(() => {
      modelStore.set(sel);
      providerService.notifyChange();
    });
    onClose();
  };

  const handleSelect = (sel: ModelSelection) => {
    if (isConfigured(sel.providerID)) {
      commit(sel);
      return;
    }
    setConfigProvider(sel.providerID);
  };

  return (
    <RoundedBox title={configProvider ? 'CONFIGURE PROVIDER' : 'MODEL PICKER'} paddingX={1}>
      {configProvider ? (
        <ProviderFlow
          initialProviderID={configProvider}
          onClose={() => setConfigProvider(null)}
          onComplete={() => {
            setConfigProvider(null);
            onClose();
          }}
        />
      ) : (
        <ModelPicker onSelect={handleSelect} onClose={onClose} onOpenProvider={onOpenProvider} />
      )}
    </RoundedBox>
  );
};
