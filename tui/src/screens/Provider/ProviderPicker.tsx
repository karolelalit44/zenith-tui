import React, { useMemo } from 'react';
import type { SearchListOption } from '../../components/ui/SearchList';
import { SearchList } from '../../components/ui/SearchList';
import { providerService } from '../../services/providers/ProviderService';
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

const POPULAR = ['nvidia', 'openai', 'anthropic', 'google', 'groq', 'openrouter'];

export const ProviderPicker: React.FC<ProviderPickerProps> = ({ providers, connected, onSelect, onClose }) => {
  const activeId = providerService.getActiveProviderId();

  const options = useMemo<SearchListOption<ProviderPickerSelection>[]>(() => {
    const list: SearchListOption<ProviderPickerSelection>[] = [];
    for (const provider of providers) {
      const isDefault = provider.id === activeId;
      list.push({
        title: provider.meta.name,
        value: { type: 'provider', providerID: provider.id, title: provider.meta.name },
        category: POPULAR.includes(provider.id) ? 'Popular' : 'Providers',
        description: isDefault ? '(default)' : undefined,
        footer: provider.hasApiKey ? 'configured' : undefined,
        gutter: connected.includes(provider.id) ? '✓' : undefined,
        current: provider.isActive,
      });
    }
    list.push({
      title: 'Other (Custom OpenAI-Compatible)',
      value: { type: 'custom', title: 'Custom OpenAI-Compatible' },
      category: 'Providers',
      description: 'Bring your own endpoint',
    });
    return list;
  }, [providers, connected, activeId]);

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
