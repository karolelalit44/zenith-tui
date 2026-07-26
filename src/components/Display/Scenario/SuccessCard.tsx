import { Box, Text } from 'ink';
import React from 'react';
import { useTheme } from '../../../theme/ThemeContext';
import type { SuccessEvent } from '../../../types/scenario';

interface SuccessCardProps {
  event: SuccessEvent;
}

export const SuccessCard: React.FC<SuccessCardProps> = React.memo(({ event }) => {
  const { theme } = useTheme();

  const details: string[] = [];
  if (event.iterations !== undefined) {
    details.push(`${event.iterations} iter${event.iterations === 1 ? '' : 's'}`);
  }
  if (event.tokenInfo) {
    details.push(`${event.tokenInfo.used} tokens (${Math.round(event.tokenInfo.percent * 100)}%)`);
  }

  return (
    <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
      <Box
        flexDirection="row"
        width="100%"
        borderStyle="round"
        borderColor={theme.colors.status.success}
        alignItems="center"
        justifyContent="space-between"
        paddingX={1}
        paddingY={0}
      >
        <Box flexDirection="row" alignItems="center" flexShrink={1}>
          <Text color={theme.colors.status.success} bold>
            ✓ [SUCCESS]{' '}
          </Text>
          <Text color={theme.colors.text.bright}>{event.message || 'Completed successfully'}</Text>
        </Box>

        {details.length > 0 && (
          <Box flexDirection="row" alignItems="center" flexShrink={0} paddingLeft={2}>
            <Text color={theme.colors.text.muted}>{details.join(' · ')}</Text>
          </Box>
        )}
      </Box>
    </Box>
  );
});
