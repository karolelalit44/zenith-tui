import React from 'react';
import { Box, Text } from 'ink';
import { useTheme } from '../../../theme/ThemeContext';
import { SuccessEvent } from '../../../types/scenario';

interface SuccessCardProps {
  event: SuccessEvent;
}

export const SuccessCard: React.FC<SuccessCardProps> = ({ event }) => {
  const { theme } = useTheme();

  return (
    <Box flexDirection="column" marginBottom={1} paddingX={1}>
      <Box flexDirection="row" alignItems="center" marginBottom={1}>
        <Text color={theme.colors.text.emerald} bold>✔ {event.message}</Text>
      </Box>

      {event.filesCreated.length > 0 && (
        <Box flexDirection="column" paddingLeft={2}>
          <Text color={theme.colors.text.muted}>Files created:</Text>
          {event.filesCreated.map((file, idx) => (
            <Box key={idx} flexDirection="row">
              <Text color={theme.colors.text.muted}>  </Text>
              <Text color={theme.colors.text.emerald}>✦</Text>
              <Text color={theme.colors.text.ethereal}> {file}</Text>
            </Box>
          ))}
        </Box>
      )}

      {event.commandsExecuted.length > 0 && (
        <Box flexDirection="column" paddingLeft={2} marginTop={1}>
          <Text color={theme.colors.text.muted}>Commands executed:</Text>
          {event.commandsExecuted.map((cmd, idx) => (
            <Box key={idx} flexDirection="row">
              <Text color={theme.colors.text.muted}>  </Text>
              <Text color={theme.colors.text.emerald}>$</Text>
              <Text color={theme.colors.text.ethereal}> {cmd}</Text>
            </Box>
          ))}
        </Box>
      )}
    </Box>
  );
};
