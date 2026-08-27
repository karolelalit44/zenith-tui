import React, { useEffect, useMemo, useState } from 'react';
import type { SearchListOption } from '../../components/ui/SearchList';
import { SearchList } from '../../components/ui/SearchList';
import { providerRepository } from '../../services/providers/ProviderRepository';
import type { ModelSelection, ProviderModelInfo, ProviderState } from '../../services/providers/types';

interface ModelPickerProps {
  provider: ProviderState;
  onSelect: (sel: ModelSelection) => void;
  onClose: () => void;
}

/**
 * Inline model chooser for the /provider setup flow (one provider at a
 * time — there is no global model switcher; the active model comes from
 * the provider's saved config). Names come from the backend models API.
 */
export const ModelPicker: React.FC<ModelPickerProps> = ({ provider, onSelect, onClose }) => {
  const [models, setModels] = useState<ProviderModelInfo[] | null>(null);

  useEffect(() => {
    let alive = true;
    providerRepository
      .fetchAllModels(provider.id)
      .then((list) => {
        if (alive) setModels(list);
      })
      .catch(() => {
        if (alive) setModels([]);
      });
    return () => {
      alive = false;
    };
  }, [provider.id]);

  const options = useMemo<SearchListOption<ModelSelection>[]>(() => {
    let entries: { id: string; name: string }[];
    if (models && models.length > 0) {
      entries = models.map((m) => ({ id: m.id, name: m.name }));
    } else {
      // Fallback while loading or when the catalog has no named models.
      entries =
        provider.meta.availableModels && provider.meta.availableModels.length > 0
          ? provider.meta.availableModels.map((m) => ({ id: m.id, name: m.name }))
          : provider.meta.defaultModel
            ? [{ id: provider.meta.defaultModel, name: provider.meta.defaultModel }]
            : [];
    }
    return entries.map((entry) => ({
      title: entry.name || entry.id,
      value: { providerID: provider.id, modelID: entry.id },
      category: entry.id === provider.meta.defaultModel ? 'Default' : undefined,
      description: entry.id,
    }));
  }, [provider, models]);

  return (
    <SearchList
      title={`Choose a model — ${provider.meta.name || provider.id}`}
      placeholder="Enter to select · ↑↓ to navigate"
      filterPlaceholder="Search models"
      options={options}
      onSelect={(option) => onSelect(option.value)}
      onClose={onClose}
    />
  );
};
