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
  if (event.filesCreated && event.filesCreated.length > 0) {
    details.push(`${event.filesCreated.length} file${event.filesCreated.length === 1 ? '' : 's'} created`);
  }
  if (event.commandsExecuted && event.commandsExecuted.length > 0) {
    details.push(`${event.commandsExecuted.length} cmd${event.commandsExecuted.length === 1 ? '' : 's'}`);
  }

  return (
    <Box
      flexDirection="row"
      width="100%"
      alignItems="center"
      justifyContent="space-between"
      marginBottom={1}
      paddingX={1}
    >
      <Box flexDirection="row" alignItems="center" flexShrink={1}>
        <Text color={theme.colors.status.success} bold>
          ✔ [SUCCESS]{' '}
        </Text>
        <Text color={theme.colors.text.bright}>{event.message || 'Completed successfully'}</Text>
      </Box>

      {details.length > 0 && (
        <Box flexDirection="row" alignItems="center" flexShrink={0} paddingLeft={2}>
          <Text color={theme.colors.text.muted}>{details.join(' · ')}</Text>
        </Box>
      )}
    </Box>
  );
});
