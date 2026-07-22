import { Box, Text, useInput } from 'ink';
import React, { useState } from 'react';
import { GenericProviderConfigForm } from '../../components/Providers/GenericProviderConfigForm';
import { ProviderList } from '../../components/Providers/ProviderList';
import { RoundedBox } from '../../components/ui/RoundedBox';
import { providerService } from '../../services/providers/ProviderService';
import type { ProviderState } from '../../services/providers/types';
import { useTheme } from '../../theme/ThemeContext';

interface ProvidersScreenProps {
  onClose: () => void;
}

export const ProvidersScreen: React.FC<ProvidersScreenProps> = ({ onClose }) => {
  const { theme } = useTheme();
  const [providers, setProviders] = useState<ProviderState[]>(() => providerService.getAllProviders());
  const activeId = providerService.getActiveProviderId();
  const initialIdx = providers.findIndex((p) => p.id === activeId);

  const [selectedIndex, setSelectedIndex] = useState(initialIdx >= 0 ? initialIdx : 0);
  const [viewMode, setViewMode] = useState<'list' | 'config'>('list');

  const selectedProvider = providers[selectedIndex] || providers[0];

  const refreshState = () => {
    setProviders(providerService.getAllProviders());
  };

  useInput((char, key) => {
    if (viewMode === 'list') {
      if (key.upArrow) {
        setSelectedIndex((prev) => Math.max(0, prev - 1));
      }

      if (key.downArrow) {
        setSelectedIndex((prev) => Math.min(providers.length - 1, prev + 1));
      }

      // Activate provider: Space or 'a' or 'A'
      if (char === ' ' || char === 'a' || char === 'A') {
        providerService.setActiveProvider(selectedProvider.id);
        refreshState();
      }

      // Open Config Form: Enter or Right Arrow
      if (key.return || key.rightArrow) {
        setViewMode('config');
      }

      if (key.escape) {
        onClose();
      }
    } else {
      // Config mode: Back to list on Escape
      if (key.escape) {
        setViewMode('list');
        refreshState();
      }
    }
  });

  return (
    <RoundedBox title="AI PROVIDER MANAGEMENT" borderColor={theme.colors.border.active} hasShadow={true}>
      <Box flexDirection="column" paddingX={2} paddingY={1} width="100%">
        {/* Navigation Mode Banner */}
        <Box
          marginBottom={1}
          paddingBottom={1}
          borderStyle="single"
          borderBottom={true}
          borderColor={theme.colors.border.muted}
          flexDirection="row"
          justifyContent="space-between"
          alignItems="center"
        >
          <Box flexDirection="row" alignItems="center">
            <Text color={theme.colors.text.emerald}>❯ </Text>
            <Text color={theme.colors.text.ethereal} bold>
              {viewMode === 'list' ? 'Select & Activate AI Provider' : `Configure ${selectedProvider.meta.name}`}
            </Text>
          </Box>

          <Box flexDirection="row">
            <Text color={theme.colors.text.muted}>Active: </Text>
            <Text color={theme.colors.status.success} bold>
              {providerService.getActiveProvider().meta.name} ({providerService.getActiveProvider().config.model})
            </Text>
          </Box>
        </Box>

        {viewMode === 'list' ? (
          <Box flexDirection="column">
            <ProviderList providers={providers} selectedIndex={selectedIndex} />
          </Box>
        ) : (
          <Box flexDirection="column">
            <GenericProviderConfigForm
              providerId={selectedProvider.id}
              onSaved={refreshState}
              onBack={() => setViewMode('list')}
            />
          </Box>
        )}

        {/* Footer Shortcut Instructions */}
        <Box marginTop={1} paddingTop={1} borderStyle="single" borderTop={true} borderColor={theme.colors.border.muted}>
          {viewMode === 'list' ? (
            <Text color={theme.colors.text.muted}>
              <Text color={theme.colors.text.emerald}>[↑/↓]</Text> Navigate Providers ·{' '}
              <Text color={theme.colors.text.emerald}>[Space/A]</Text> Activate Provider ·{' '}
              <Text color={theme.colors.text.emerald}>[Enter]</Text> Edit Config ·{' '}
              <Text color={theme.colors.text.emerald}>[Esc]</Text> Exit
            </Text>
          ) : (
            <Text color={theme.colors.text.muted}>
              <Text color={theme.colors.text.emerald}>[↑/↓]</Text> Navigate Fields ·{' '}
              <Text color={theme.colors.text.emerald}>[Enter]</Text> Edit Field ·{' '}
              <Text color={theme.colors.text.emerald}>[Ctrl+S]</Text> Save Config ·{' '}
              <Text color={theme.colors.text.emerald}>[Esc]</Text> Back to List
            </Text>
          )}
        </Box>
      </Box>
    </RoundedBox>
  );
};
