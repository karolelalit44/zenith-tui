import { Box, Text } from 'ink';
import React from 'react';
import { useTheme } from '../../../theme/ThemeContext';
import type { RetryEvent } from '../../../types/scenario';

interface RetryBlockProps {
  event: RetryEvent;
}

export const RetryBlock: React.FC<RetryBlockProps> = React.memo(({ event }) => {
  const { theme } = useTheme();

  return (
    <Box flexDirection="row" width="100%" marginBottom={1} paddingX={1} alignItems="center">
      <Text color={theme.colors.status.warning} bold>
        [RETRY] #{event.attempt}
      </Text>
      <Text color={theme.colors.text.muted}> · </Text>
      <Text color={theme.colors.text.ethereal}>{event.message}</Text>
    </Box>
  );
});
