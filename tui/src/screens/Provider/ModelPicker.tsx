import React, { useEffect, useMemo, useState } from 'react';
import type { SearchListAction, SearchListOption } from '../../components/ui/SearchList';
import { SearchList } from '../../components/ui/SearchList';
import { modelStore } from '../../services/providers/ModelStore';
import { providerRepository } from '../../services/providers/ProviderRepository';
import type { ModelSelection } from '../../services/providers/types';

interface ModelPickerProps {
  /** Restrict the list to a single provider (used right after validation). */
  providerID?: string;
  /** When provided, adds a "View all providers" action that jumps to the provider flow. */
  onOpenProvider?: () => void;
  onSelect: (sel: ModelSelection) => void;
  onClose: () => void;
}

const key = (sel: ModelSelection): string => `${sel.providerID}/${sel.modelID}`;

export const ModelPicker: React.FC<ModelPickerProps> = ({ providerID, onOpenProvider, onSelect, onClose }) => {
  const [, force] = useState(0);

  useEffect(() => {
    const unsubscribe = modelStore.subscribe(() => force((v) => v + 1));
    return unsubscribe;
  }, []);

  const providers = useMemo(() => {
    const list = providerRepository
      .getProviderInfoList()
      .filter((provider) => !providerID || provider.id === providerID);
    if (providerID) return list;
    return list.filter(
      (provider) => provider.has_api_key || provider.validation_status === 'validated' || provider.is_active,
    );
  }, [providerID]);

  const provider = useMemo(
    () => (providerID ? providerRepository.getProviderInfo(providerID) : undefined),
    [providerID],
  );

  const exists = useMemo(
    () => (sel: ModelSelection) => {
      const item = providers.find((p) => p.id === sel.providerID);
      if (!item) return false;
      return Boolean(item.models[sel.modelID]) || item.model === sel.modelID;
    },
    [providers],
  );

  const options = useMemo<SearchListOption<ModelSelection>[]>(() => {
    const isCurrent = (sel: ModelSelection): boolean =>
      Boolean(
        modelStore.current &&
          modelStore.current.providerID === sel.providerID &&
          modelStore.current.modelID === sel.modelID,
      );
    const modelName = (sel: ModelSelection): string => {
      const item = providers.find((p) => p.id === sel.providerID);
      return item?.models[sel.modelID]?.name ?? sel.modelID;
    };
    const providerName = (sel: ModelSelection): string | undefined =>
      providers.find((p) => p.id === sel.providerID)?.name;

    const list: SearchListOption<ModelSelection>[] = [];

    const favorites = modelStore.favorite.filter(exists);
    for (const sel of favorites) {
      list.push({
        title: modelName(sel),
        description: providerName(sel),
        value: sel,
        category: 'Favorites',
        current: isCurrent(sel),
      });
    }

    const favoriteKeys = new Set(favorites.map(key));
    const recents = modelStore.recent.filter((sel) => exists(sel) && !favoriteKeys.has(key(sel)));
    for (const sel of recents) {
      list.push({
        title: modelName(sel),
        description: providerName(sel),
        value: sel,
        category: 'Recent',
        current: isCurrent(sel),
      });
    }
    const listedKeys = new Set([...favoriteKeys, ...recents.map(key)]);

    for (const item of providers) {
      const seen = new Set<string>();
      for (const model of Object.values(item.models)) {
        const sel: ModelSelection = { providerID: item.id, modelID: model.id };
        const optionKey = key(sel);
        if (seen.has(optionKey) || listedKeys.has(optionKey)) continue;
        seen.add(optionKey);
        list.push({
          title: model.name || model.id,
          value: sel,
          category: item.name,
          description: model.description || (favoriteKeys.has(optionKey) ? '(Favorite)' : undefined),
          footer: model.is_default ? 'default' : undefined,
          current: isCurrent(sel),
        });
      }
    }
    return list;
  }, [providers, exists]);

  const toggleFavorite = (sel: ModelSelection) => {
    modelStore.toggleFavorite(sel);
  };

  const actions: SearchListAction<ModelSelection>[] = [];
  if (onOpenProvider) {
    actions.push({
      label: 'View all providers',
      onTrigger: () => onOpenProvider(),
    });
  }
  actions.push({
    label: '★ Favorite',
    onTrigger: (option) => toggleFavorite(option.value),
  });

  return (
    <SearchList
      title={providerID ? (provider?.name ?? providerID) : 'Select a model'}
      placeholder="Enter to use · Tab for actions"
      filterPlaceholder="Search models"
      options={options}
      actions={actions}
      onSelect={(option) => onSelect(option.value)}
      onClose={onClose}
    />
  );
};
