import { Box, Text } from 'ink';
import React from 'react';
import { formatTokenCount } from '../../../services/api/tokenEstimationService';
import { useTheme } from '../../../theme/ThemeContext';
import type { SuccessEvent, TurnManifestEvent } from '../../../types/scenario';
import { formatDuration } from '../../../utils/text';

interface SuccessCardProps {
  event: SuccessEvent;
  manifest?: TurnManifestEvent;
}

export const SuccessCard: React.FC<SuccessCardProps> = React.memo(({ event, manifest }) => {
  const { theme } = useTheme();

  const parts: string[] = [];
  if (manifest && manifest.created.length > 0) {
    parts.push(`${manifest.created.length} file${manifest.created.length === 1 ? '' : 's'} created`);
  }
  if (event.iterations !== undefined) {
    parts.push(`${event.iterations} iter${event.iterations === 1 ? '' : 's'}`);
  }
  if (event.tokenInfo) {
    parts.push(`${formatTokenCount(event.tokenInfo.used)} tokens`);
  }
  if (event.elapsedMs !== undefined) {
    parts.push(formatDuration(event.elapsedMs));
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
