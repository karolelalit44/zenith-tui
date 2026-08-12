import React, { useMemo } from 'react';
import type { SearchListOption } from '../../components/ui/SearchList';
import { SearchList } from '../../components/ui/SearchList';
import type { ProviderCatalogItem } from '../../services/providers/types';

export interface ProviderPickerSelection {
  type: 'provider' | 'custom';
  providerID?: string;
  title: string;
}

interface ProviderPickerProps {
  providers: ProviderCatalogItem[];
  onSelect: (selection: ProviderPickerSelection) => void;
  onClose: () => void;
}

/**
 * Shared provider selector. Both keyboard navigation and search resolve to the
 * same ProviderPickerSelection value and the same onSelect handler, so there is
 * exactly one selection path (defaults, search, keyboard, mouse).
 */
export const ProviderPicker: React.FC<ProviderPickerProps> = ({ providers, onSelect, onClose }) => {
  const options = useMemo<SearchListOption<ProviderPickerSelection>[]>(() => {
    const list: SearchListOption<ProviderPickerSelection>[] = [];
    for (const provider of providers) {
      const isCustom = provider.type === 'custom';
      list.push({
        title: provider.name,
        value: {
          type: isCustom ? 'custom' : 'provider',
          providerID: provider.id,
          title: provider.name,
        },
        category: isCustom ? 'Custom' : 'Default',
        description: isCustom ? 'Bring your own endpoint' : undefined,
      });
    }
    return list;
  }, [providers]);

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
