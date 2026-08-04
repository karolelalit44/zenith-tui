import { Box, Text } from 'ink';
import React from 'react';
import { formatTokenCount } from '../../../services/api/tokenEstimationService';
import { useTheme } from '../../../theme/ThemeContext';
import type { SuccessEvent } from '../../../types/scenario';

interface SuccessCardProps {
  event: SuccessEvent;
}

function formatElapsed(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  const totalSec = ms / 1000;
  if (totalSec < 60) return `${totalSec.toFixed(1)}s`;
  const mins = Math.floor(totalSec / 60);
  const secs = Math.round(totalSec % 60);
  if (mins < 60) return secs > 0 ? `${mins}m ${secs}s` : `${mins}m`;
  const hrs = Math.floor(mins / 60);
  const remMins = mins % 60;
  return remMins > 0 ? `${hrs}h ${remMins}m` : `${hrs}h`;
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
  if (event.elapsedMs !== undefined) {
    parts.push(formatElapsed(event.elapsedMs));
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
