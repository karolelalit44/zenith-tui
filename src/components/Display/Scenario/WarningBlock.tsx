import React from 'react';
import { Box, Text } from 'ink';
import { useTheme } from '../../../theme/ThemeContext';
import { WarningEvent } from '../../../types/scenario';

interface WarningBlockProps {
  event: WarningEvent;
}

export const WarningBlock: React.FC<WarningBlockProps> = ({ event }) => {
  const { theme } = useTheme();

  return (
    <Box flexDirection="column" marginBottom={1} paddingX={1}>
      <Box flexDirection="row" alignItems="center" marginBottom={1}>
        <Text color={theme.colors.text.warning} bold>⚠ Warning</Text>
      </Box>

      <Box flexDirection="column" paddingLeft={2} borderStyle="round" borderColor={theme.colors.text.warning} paddingX={1}>
        <Text color={theme.colors.text.warning}>{event.message}</Text>
        {event.details && (
          <Box marginTop={1}>
            <Text color={theme.colors.text.muted} dimColor>{event.details}</Text>
          </Box>
        )}
      </Box>
    </Box>
  );
};
