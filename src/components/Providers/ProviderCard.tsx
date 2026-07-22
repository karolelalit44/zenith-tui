import { Box, Text } from 'ink';
import React from 'react';
import { modelService } from '../../services/providers/ModelService';
import type { ProviderState } from '../../services/providers/types';
import { useTheme } from '../../theme/ThemeContext';

interface ProviderCardProps {
  provider: ProviderState;
  isSelected: boolean;
}

export const ProviderCard: React.FC<ProviderCardProps> = ({ provider, isSelected }) => {
  const { theme } = useTheme();
  const { id, meta, config, isActive, isConfigured } = provider;
  const modelsLabel = modelService.getTotalModelsLabel(id);

  return (
    <Box flexDirection="row" alignItems="center" marginY={0} width="100%">
      <Box width={3}>
        <Text color={isSelected ? theme.colors.text.emerald : theme.colors.text.dim}>{isSelected ? '▸ ' : '  '}</Text>
      </Box>

      {/* Active Indicator Icon */}
      <Box width={3}>
        <Text color={isActive ? theme.colors.status.success : theme.colors.text.muted} bold>
          {isActive ? '✓ ' : '○ '}
        </Text>
      </Box>

      {/* Provider Name */}
      <Box width={22} flexShrink={0}>
        <Text color={isSelected ? theme.colors.text.ethereal : theme.colors.text.dim} bold={isSelected}>
          {meta.name}
        </Text>
      </Box>

      {/* Swatch */}
      <Box flexDirection="row" marginRight={2}>
        {meta.swatch.map((c, i) => (
          <Text key={i} color={c}>
            █
          </Text>
        ))}
      </Box>

      {/* Selected Model */}
      <Box width={26} flexShrink={0}>
        <Text color={theme.colors.text.muted} italic>
          {config.model || meta.defaultModel}
        </Text>
      </Box>

      {/* Total Models Count Badge */}
      <Box width={16} flexShrink={0}>
        <Text color={theme.colors.text.dim}>{modelsLabel}</Text>
      </Box>

      {/* Config & Active State Badges */}
      <Box flexDirection="row">
        {isActive ? (
          <Text color={theme.colors.status.success} bold>
            [ACTIVE]
          </Text>
        ) : isConfigured ? (
          <Text color={theme.colors.status.info} bold>
            [CONFIGURED]
          </Text>
        ) : (
          <Text color={theme.colors.status.warning} bold>
            [NOT CONFIGURED]
          </Text>
        )}
      </Box>
    </Box>
  );
};
