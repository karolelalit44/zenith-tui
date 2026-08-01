import { Box, Text } from 'ink';
import React from 'react';
import { useTheme } from '../../../theme/ThemeContext';
import type { WarningEvent } from '../../../types/scenario';

interface WarningBlockProps {
  event: WarningEvent;
}

export const WarningBlock: React.FC<WarningBlockProps> = React.memo(({ event }) => {
  const { theme } = useTheme();

  return (
    <Box flexDirection="row" width="100%" marginBottom={1} paddingX={1} alignItems="center">
      <Text color={theme.colors.status.warning} bold>
        ▲ [WARNING]{' '}
      </Text>
      <Text color={theme.colors.text.bright} wrap="wrap">
        {event.message}
      </Text>
      {event.code && <Text color={theme.colors.text.dim}> ({event.code})</Text>}
    </Box>
  );
});
