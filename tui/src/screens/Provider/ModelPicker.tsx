import React, { useEffect, useMemo, useState } from 'react';
import type { SearchListAction, SearchListOption } from '../../components/ui/SearchList';
import { SearchList } from '../../components/ui/SearchList';
import { modelStore } from '../../services/providers/ModelStore';
import { providerRepository } from '../../services/providers/ProviderRepository';
import type { ModelSelection } from '../../services/providers/types';

interface ModelPickerProps {
  /** Restrict the list to a single provider (used right after validation). */
  providerID?: string;
  onSelect: (sel: ModelSelection) => void;
  onClose: () => void;
}

export const ModelPicker: React.FC<ModelPickerProps> = ({ providerID, onSelect, onClose }) => {
  const [, force] = useState(0);

  useEffect(() => {
    const unsubscribe = modelStore.subscribe(() => force((v) => v + 1));
    return unsubscribe;
  }, []);

  const providers = useMemo(
    () => providerRepository.getProviderInfoList().filter((provider) => !providerID || provider.id === providerID),
    [providerID],
  );

  const exists = useMemo(
    () => (sel: ModelSelection) => {
      const provider = providers.find((item) => item.id === sel.providerID);
      if (!provider) return false;
      return Boolean(provider.models[sel.modelID]) || provider.model === sel.modelID;
    },
    [providers],
  );

  const options = useMemo<SearchListOption<ModelSelection>[]>(() => {
    const list: SearchListOption<ModelSelection>[] = [];
    const favorites = modelStore.favorite.filter(exists);
    for (const sel of favorites) {
      list.push({
        title: `${sel.providerID}/${sel.modelID}`,
        value: sel,
        category: 'Favorites',
        current: Boolean(
          modelStore.current &&
            modelStore.current.modelID === sel.modelID &&
            modelStore.current.providerID === sel.providerID,
        ),
      });
    }
    const recents = modelStore.recent.filter(
      (sel) => exists(sel) && !favorites.some((f) => f.modelID === sel.modelID && f.providerID === sel.providerID),
    );
    for (const sel of recents) {
      list.push({
        title: `${sel.providerID}/${sel.modelID}`,
        value: sel,
        category: 'Recent',
        current: Boolean(
          modelStore.current &&
            modelStore.current.modelID === sel.modelID &&
            modelStore.current.providerID === sel.providerID,
        ),
      });
    }
    for (const provider of providers) {
      const providerModels = Object.values(provider.models);
      const seen = new Set<string>();
      for (const model of providerModels) {
        const sel: ModelSelection = { providerID: provider.id, modelID: model.id };
        const key = `${sel.providerID}/${sel.modelID}`;
        if (seen.has(key)) continue;
        seen.add(key);
        list.push({
          title: model.name || model.id,
          value: sel,
          category: provider.name,
          description: model.description || undefined,
          footer: model.is_default ? 'default' : undefined,
          current: Boolean(
            modelStore.current &&
              modelStore.current.modelID === model.id &&
              modelStore.current.providerID === provider.id,
          ),
        });
      }
    }
    return list;
  }, [providers, exists]);

  const toggleFavorite = (sel: ModelSelection) => {
    modelStore.toggleFavorite(sel);
  };

  const actions: SearchListAction<ModelSelection>[] = [
    {
      label: '★ Favorite',
      onTrigger: (option) => toggleFavorite(option.value),
    },
  ];

  return (
    <SearchList
      title="Select a model"
      placeholder="Provider/model to use for chat."
      filterPlaceholder="Search models"
      options={options}
      actions={actions}
      onSelect={(option) => onSelect(option.value)}
      onClose={onClose}
    />
  );
};
