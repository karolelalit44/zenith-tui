import { Box, Text } from 'ink';
import React from 'react';
import { estimateTokensForEvents, formatTokenCount } from '../../../services/api/tokenEstimationService';
import { useTheme } from '../../../theme/ThemeContext';
import type { ScenarioEvent, SuccessEvent, TurnManifestEvent } from '../../../types/scenario';
import { formatDuration } from '../../../utils/text';

interface SuccessCardProps {
  event: SuccessEvent;
  manifest?: TurnManifestEvent;
  turnEvents?: ScenarioEvent[];
}

export const SuccessCard: React.FC<SuccessCardProps> = React.memo(({ event, turnEvents }) => {
  const { theme } = useTheme();

  const parts: string[] = [];
  if (event.iterations !== undefined) {
    parts.push(`${event.iterations} iter${event.iterations === 1 ? '' : 's'}`);
  }
  if (event.elapsedMs !== undefined) {
    parts.push(formatDuration(event.elapsedMs));
  }

  // Use event.tokenInfo if provided, otherwise estimate total tokens for all events in the turn
  const usedTokens = event.tokenInfo?.used ?? (turnEvents ? estimateTokensForEvents(turnEvents) : 0);
  if (usedTokens > 0) {
    parts.push(`${formatTokenCount(usedTokens)} tokens`);
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
