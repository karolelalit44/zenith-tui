import React from 'react';
import { Box, Text } from 'ink';
import { useTheme } from '../../../theme/ThemeContext';
import { WarningEvent } from '../../../types/scenario';

interface WarningBlockProps {
  event: WarningEvent;
}

export const WarningBlock: React.FC<WarningBlockProps> = React.memo(({ event }) => {
  const { theme } = useTheme();

  return (
    <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
      <Box flexDirection="column" width="100%" borderStyle="round" borderColor="#D29922" paddingX={1} paddingY={1}>
        <Box flexDirection="row" alignItems="center" marginBottom={1} flexWrap="wrap">
          <Text color="#D29922" bold>[WARNING] </Text>
          <Text color="#E6EDF3" bold>{event.message}</Text>
        </Box>

        {event.details && (
          <Box marginTop={0} paddingLeft={1}>
            <Text color="#8B949E" wrap="wrap">{event.details}</Text>
          </Box>
        )}

        <Box marginTop={1} flexDirection="row" justifyContent="flex-end">
          <Text color="#D29922" dimColor>[NON-FATAL · Execution Continuing]</Text>
        </Box>
      </Box>
    </Box>
  );
});
