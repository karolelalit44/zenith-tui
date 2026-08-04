import React, { useMemo } from 'react';
import type { SearchListOption } from '../../components/ui/SearchList';
import { SearchList } from '../../components/ui/SearchList';
import type { ProviderState } from '../../services/providers/types';

export interface ProviderPickerSelection {
  type: 'provider' | 'custom';
  providerID?: string;
  title: string;
}

interface ProviderPickerProps {
  providers: ProviderState[];
  connected: string[];
  onSelect: (selection: ProviderPickerSelection) => void;
  onClose: () => void;
}

export const ProviderPicker: React.FC<ProviderPickerProps> = ({ providers, connected, onSelect, onClose }) => {
  const options = useMemo<SearchListOption<ProviderPickerSelection>[]>(() => {
    // Custom-flow providers (SQL catalog custom_flow flag) are surfaced as a
    // single aggregated "bring your own endpoint" entry.
    const customProvider = providers.find((provider) => provider.isCustomFlow);
    const list: SearchListOption<ProviderPickerSelection>[] = [];
    for (const provider of providers) {
      if (provider.isCustomFlow) continue;
      list.push({
        title: provider.meta.name,
        value: { type: 'provider', providerID: provider.id, title: provider.meta.name },
        category: provider.isPopular ? 'Popular' : 'Providers',
        footer: provider.hasApiKey ? 'configured' : undefined,
        gutter: connected.includes(provider.id) ? '✓' : undefined,
        current: provider.isActive,
      });
    }
    if (customProvider) {
      list.push({
        title: 'Other (Custom OpenAI-Compatible)',
        value: { type: 'custom', providerID: customProvider.id, title: 'Custom OpenAI-Compatible' },
        category: 'Providers',
        description: 'Bring your own endpoint',
      });
    }
    return list;
  }, [providers, connected]);

  return (
    <SearchList
      title="Choose a provider"
      placeholder="Enter to configure · ↑↓ to navigate"
      filterPlaceholder="Search providers"
      options={options}
      onSelect={(option) => onSelect(option.value)}
      onClose={onClose}
    />
  );
};
