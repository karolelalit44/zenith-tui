import { Box, Text } from 'ink';
import React from 'react';
import { useTheme } from '../../../theme/ThemeContext';
import type { SuccessEvent } from '../../../types/scenario';

interface SuccessCardProps {
  event: SuccessEvent;
}

export const SuccessCard: React.FC<SuccessCardProps> = React.memo(({ event }) => {
  const { theme } = useTheme();

  return (
    <Box flexDirection="column" marginBottom={1} paddingX={1}>
      <Box flexDirection="row" alignItems="center" marginBottom={0}>
        <Text color={theme.colors.status.success} bold>
          [SUCCESS] {event.message}
        </Text>
      </Box>

      {event.filesCreated.length > 0 && (
        <Box flexDirection="column" paddingLeft={1} marginTop={0}>
          <Text color={theme.colors.text.muted}>Files created:</Text>
          {event.filesCreated.map((file, idx) => (
            <Box key={idx} flexDirection="row">
              <Text color={theme.colors.status.success}>▸ </Text>
              <Text color={theme.colors.text.bright}> {file}</Text>
            </Box>
          ))}
        </Box>
      )}

      {event.commandsExecuted.length > 0 && (
        <Box flexDirection="column" paddingLeft={1} marginTop={0}>
          <Text color={theme.colors.text.muted}>Commands executed:</Text>
          {event.commandsExecuted.map((cmd, idx) => (
            <Box key={idx} flexDirection="row">
              <Text color={theme.colors.status.success}>$ </Text>
              <Text color={theme.colors.text.bright}> {cmd}</Text>
            </Box>
          ))}
        </Box>
      )}
    </Box>
  );
});
