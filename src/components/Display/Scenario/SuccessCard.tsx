import { Box, Text } from 'ink';
import React from 'react';
import { useTheme } from '../../../theme/ThemeContext';
import type { SuccessEvent } from '../../../types/scenario';
import { formatTokenCount } from '../../../services/data/tokenEstimationService';

interface SuccessCardProps {
  event: SuccessEvent;
}

export const SuccessCard: React.FC<SuccessCardProps> = React.memo(({ event }) => {
  const { theme } = useTheme();

  const parts: string[] = [];
  if (event.iterations !== undefined) {
    parts.push(`${event.iterations} iter${event.iterations === 1 ? '' : 's'}`);
  }
  if (event.tokenInfo) {
    parts.push(`${formatTokenCount(event.tokenInfo.used)} tokens`);
  }

  return (
    <Box flexDirection="column" width="100%" paddingX={1} marginBottom={1}>
      <Box flexDirection="row" alignItems="center">
        <Text color={theme.colors.status.success}>✓ </Text>
        {parts.length > 0 ? (
          <Text color={theme.colors.text.muted}>{parts.join(' · ')}</Text>
        ) : (
          <Text color={theme.colors.text.muted}>done</Text>
        )}
      </Box>
    </Box>
  );
});
