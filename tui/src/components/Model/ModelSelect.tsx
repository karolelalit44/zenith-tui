import React, { useEffect, useMemo, useState } from 'react';
import { modelStore } from '../../services/providers/ModelStore';
import { providerRepository } from '../../services/providers/ProviderRepository';
import type { ModelSelection } from '../../services/providers/types';
import type { SearchListAction, SearchListOption } from '../ui/SearchList';
import { SearchList } from '../ui/SearchList';

interface ModelSelectProps {
  providerID: string;
  onSelect: (sel: ModelSelection) => void;
  onBack: () => void;
}

export const ModelSelect: React.FC<ModelSelectProps> = ({ providerID, onSelect, onBack }) => {
  const [, force] = useState(0);

  useEffect(() => {
    const unsubscribe = modelStore.subscribe(() => force((v) => v + 1));
    return unsubscribe;
  }, []);

  const provider = providerRepository.getProviderInfo(providerID);

  const options = useMemo<SearchListOption<ModelSelection>[]>(() => {
    const exists = (sel: ModelSelection): boolean =>
      Boolean(provider?.models[sel.modelID]) || provider?.model === sel.modelID;
    const current = modelStore.current;

    const isCurrent = (sel: ModelSelection): boolean =>
      Boolean(current && current.providerID === sel.providerID && current.modelID === sel.modelID);

    const list: SearchListOption<ModelSelection>[] = [];
    const favorites = modelStore.favorite.filter(exists);
    for (const sel of favorites) {
      list.push({
        title: sel.modelID,
        value: sel,
        category: 'Favorites',
        current: isCurrent(sel),
      });
    }

    const recents = modelStore.recent.filter((sel) => exists(sel) && !favorites.some((f) => f.modelID === sel.modelID));
    for (const sel of recents) {
      list.push({
        title: sel.modelID,
        value: sel,
        category: 'Recent',
        current: isCurrent(sel),
      });
    }

    if (provider) {
      const seen = new Set<string>([...favorites, ...recents].map((s) => s.modelID));
      for (const model of Object.values(provider.models)) {
        if (seen.has(model.id)) continue;
        seen.add(model.id);
        list.push({
          title: model.name || model.id,
          value: { providerID, modelID: model.id },
          category: 'Models',
          description: model.description || undefined,
          footer: model.is_default ? 'default' : undefined,
          current: isCurrent({ providerID, modelID: model.id }),
        });
      }
    }

    return list;
  }, [provider, providerID]);

  const actions: SearchListAction<ModelSelection>[] = [
    {
      label: '★ Favorite',
      onTrigger: (option) => {
        modelStore.toggleFavorite(option.value);
      },
    },
  ];

  return (
    <SearchList
      title={`Select a model · ${provider?.name ?? providerID}`}
      placeholder="Enter to use · Tab to favorite · esc for providers"
      filterPlaceholder="Search models"
      options={options}
      actions={actions}
      onSelect={(option) => onSelect(option.value)}
      onClose={onBack}
    />
  );
};
