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
    <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
      <Box
        flexDirection="column"
        width="100%"
        borderStyle="round"
        borderColor={theme.colors.status.warning}
        paddingX={1}
        paddingY={1}
      >
        <Box flexDirection="row" alignItems="center" marginBottom={1} flexWrap="wrap">
          <Text color={theme.colors.status.warning} bold>
            [WARNING]{' '}
          </Text>
          <Text color={theme.colors.text.bright} bold>
            {event.message}
          </Text>
        </Box>

        {event.details && (
          <Box marginTop={0} paddingLeft={1}>
            <Text color={theme.colors.text.muted} wrap="wrap">
              {event.details}
            </Text>
          </Box>
        )}

        <Box marginTop={1} flexDirection="row" justifyContent="flex-end">
          <Text color={theme.colors.status.warning} dimColor>
            [NON-FATAL · Execution Continuing]
          </Text>
        </Box>
      </Box>
    </Box>
  );
});
