import React, { useMemo } from 'react';
import { modelStore } from '../../services/providers/ModelStore';
import { providerRepository } from '../../services/providers/ProviderRepository';
import type { ProviderInfo } from '../../services/providers/types';
import type { SearchListOption } from '../ui/SearchList';
import { SearchList } from '../ui/SearchList';

interface ProviderSelectProps {
  onSelect: (provider: ProviderInfo) => void;
  onClose: () => void;
}

export const ProviderSelect: React.FC<ProviderSelectProps> = ({ onSelect, onClose }) => {
  const options = useMemo<SearchListOption<ProviderInfo>[]>(() => {
    const isConfigured = (provider: ProviderInfo): boolean =>
      Boolean(provider.has_api_key) || provider.validation_status === 'validated' || provider.is_active;

    return providerRepository
      .getProviderInfoList()
      .filter((provider) => isConfigured(provider) && Object.keys(provider.models).length > 0)
      .map((provider) => ({
        title: `${modelStore.current?.providerID === provider.id ? '● ' : ''}${provider.name}`,
        value: provider,
        category: provider.is_popular ? 'Popular' : 'Providers',
        description: provider.model ? `default: ${provider.model}` : undefined,
        gutter: isConfigured(provider) ? '✓' : undefined,
      }));
  }, []);

  return (
    <SearchList
      title="Select a provider"
      placeholder="Enter to pick a model · ↑↓ to navigate"
      filterPlaceholder="Search providers"
      options={options}
      onSelect={(option) => onSelect(option.value)}
      onClose={onClose}
    />
  );
};
