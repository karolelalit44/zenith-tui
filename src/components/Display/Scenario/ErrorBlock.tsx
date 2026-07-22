import React from 'react';
import { Box, Text } from 'ink';
import { useTheme } from '../../../theme/ThemeContext';
import { ErrorEvent } from '../../../types/scenario';

interface ErrorBlockProps {
  event: ErrorEvent;
}

export const ErrorBlock: React.FC<ErrorBlockProps> = React.memo(({ event }) => {
  const { theme } = useTheme();

  return (
    <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
      <Box flexDirection="column" width="100%" borderStyle="round" borderColor="#F85149" paddingX={1} paddingY={1}>
        <Box flexDirection="row" alignItems="center" marginBottom={1} flexWrap="wrap">
          <Text color="#F85149" bold>[ERROR] </Text>
          <Text color="#E6EDF3" bold>{event.message}</Text>
          {event.command && (
            <Text color="#8B949E"> (command: {event.command})</Text>
          )}
        </Box>

        {event.stack && (
          <Box flexDirection="column" marginBottom={1} paddingLeft={1} backgroundColor="#21262D">
            <Text color="#F85149" dimColor wrap="wrap">{event.stack}</Text>
          </Box>
        )}

        <Box flexDirection="row" alignItems="center" justifyContent="space-between" flexWrap="wrap" marginTop={1}>
          <Text color="#8B949E">Recommendation: Check credentials, permissions, or project config.</Text>
          <Box paddingX={1} backgroundColor="#F85149">
            <Text color="#000000" bold>[RETRY AVAILABLE]</Text>
          </Box>
        </Box>
      </Box>
    </Box>
  );
});
