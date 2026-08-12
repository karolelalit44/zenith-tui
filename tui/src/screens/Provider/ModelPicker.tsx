import { Box, Text } from 'ink';
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import type { SearchListAction, SearchListOption } from '../../components/ui/SearchList';
import { SearchList } from '../../components/ui/SearchList';
import { modelStore } from '../../services/providers/ModelStore';
import { providerRepository } from '../../services/providers/ProviderRepository';
import { MODELS_PER_PAGE, type ModelSelection, type ProviderModelInfo } from '../../services/providers/types';
import { useTheme } from '../../theme/ThemeContext';

interface ModelPickerProps {
  /** When set, fetch that provider's models from the backend (shared selector). */
  providerID?: string;
  providerName?: string;

  onOpenProvider?: () => void;
  onSelect: (sel: ModelSelection) => void;
  onClose: () => void;
}

const key = (sel: ModelSelection): string => `${sel.providerID}/${sel.modelID}`;

/**
 * Shared, reusable model selector. When a providerID is passed (default-provider
 * setup flow) it fetches that provider's models from the backend and paginates
 * them 5 per page. Without a providerID it renders the cross-provider model menu.
 */
export const ModelPicker: React.FC<ModelPickerProps> = ({
  providerID,
  providerName,
  onOpenProvider,
  onSelect,
  onClose,
}) => {
  const { theme } = useTheme();
  const [, force] = useState(0);
  const [fetched, setFetched] = useState<ProviderModelInfo[]>([]);
  const [loading, setLoading] = useState(Boolean(providerID));
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    const unsubscribe = modelStore.subscribe(() => force((v) => v + 1));
    return unsubscribe;
  }, []);

  useEffect(() => {
    if (!providerID) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setLoadError(null);
    providerRepository
      .fetchAllModels(providerID)
      .then((list) => {
        if (cancelled) return;
        setFetched(list);
        setLoading(false);
      })
      .catch(() => {
        if (cancelled) return;
        setLoadError('Failed to load models.');
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [providerID]);

  const isCurrent = useCallback(
    (sel: ModelSelection): boolean =>
      Boolean(
        modelStore.current &&
          modelStore.current.providerID === sel.providerID &&
          modelStore.current.modelID === sel.modelID,
      ),
    [],
  );

  const baseProviders = useMemo(() => providerRepository.getProviderInfoList(), []);

  const modelOptions = useMemo<SearchListOption<ModelSelection>[]>(() => {
    if (!providerID) return [];
    const list: SearchListOption<ModelSelection>[] = [];
    const seen = new Set<string>();
    for (const model of fetched) {
      const sel: ModelSelection = { providerID, modelID: model.id };
      const optionKey = key(sel);
      if (seen.has(optionKey)) continue;
      seen.add(optionKey);
      list.push({
        title: model.name || model.id,
        value: sel,
        description: model.description || undefined,
        footer: model.is_default ? 'default' : undefined,
        current: isCurrent(sel),
      });
    }
    return list;
  }, [providerID, fetched, isCurrent]);

  const allOptions = useMemo<SearchListOption<ModelSelection>[]>(() => {
    const modelName = (sel: ModelSelection): string => {
      const item = baseProviders.find((p) => p.id === sel.providerID);
      return item?.models[sel.modelID]?.name ?? sel.modelID;
    };
    const providerNameFor = (sel: ModelSelection): string | undefined =>
      baseProviders.find((p) => p.id === sel.providerID)?.name;
    const providers = baseProviders.filter(
      (provider) => provider.has_api_key || provider.validation_status === 'validated' || provider.is_active,
    );
    const exists = (sel: ModelSelection): boolean => {
      const item = providers.find((p) => p.id === sel.providerID);
      if (!item) return false;
      return Boolean(item.models[sel.modelID]) || item.model === sel.modelID;
    };

    const list: SearchListOption<ModelSelection>[] = [];
    const favorites = modelStore.favorite.filter(exists);
    for (const sel of favorites) {
      list.push({
        title: modelName(sel),
        description: providerNameFor(sel),
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
        description: providerNameFor(sel),
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
  }, [baseProviders, isCurrent]);

  const options = providerID ? modelOptions : allOptions;

  const actions: SearchListAction<ModelSelection>[] = [];
  if (onOpenProvider) {
    actions.push({
      label: 'View all providers',
      onTrigger: () => onOpenProvider(),
    });
  }
  if (!providerID) {
    actions.push({
      label: '★ Favorite',
      onTrigger: (option) => modelStore.toggleFavorite(option.value),
    });
  }

  if (providerID && loading) {
    return (
      <Box flexDirection="column" width="100%" paddingLeft={2} paddingRight={2} paddingTop={1}>
        <Box flexDirection="row" justifyContent="space-between">
          <Text color={theme.colors.text.ethereal} bold>
            {providerName ?? providerID}
          </Text>
          <Text color={theme.colors.text.muted}>esc</Text>
        </Box>
        <Text color={theme.colors.text.muted}>Loading models…</Text>
      </Box>
    );
  }

  if (providerID && loadError && options.length === 0) {
    return (
      <Box flexDirection="column" width="100%" paddingLeft={2} paddingRight={2} paddingTop={1}>
        <Text color={theme.colors.status.error} bold>
          Failed to load models
        </Text>
        <Text color={theme.colors.text.ethereal}>{loadError}</Text>
        <Text color={theme.colors.text.muted}>Press Esc to go back.</Text>
      </Box>
    );
  }

  if (providerID && options.length === 0) {
    return (
      <Box flexDirection="column" width="100%" paddingLeft={2} paddingRight={2} paddingTop={1}>
        <Text color={theme.colors.text.ethereal} bold>
          No models found for this provider.
        </Text>
        <Text color={theme.colors.text.muted}>Press Esc to go back.</Text>
      </Box>
    );
  }

  return (
    <SearchList
      title={providerID ? (providerName ?? providerID) : 'Select a model'}
      placeholder="Enter to use · ↑↓ to navigate"
      filterPlaceholder="Search models"
      options={options}
      actions={actions}
      pageSize={providerID ? MODELS_PER_PAGE : undefined}
      onSelect={(option) => onSelect(option.value)}
      onClose={onClose}
    />
  );
};
