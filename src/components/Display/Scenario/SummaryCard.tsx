import { Box, Text } from 'ink';
import React from 'react';
import { useTheme } from '../../../theme/ThemeContext';
import type { SummaryEvent } from '../../../types/scenario';

interface SummaryCardProps {
  event: SummaryEvent;
}

export const SummaryCard: React.FC<SummaryCardProps> = React.memo(({ event }) => {
  const { theme } = useTheme();

  return (
    <Box flexDirection="column" marginTop={1} marginBottom={1} paddingX={1}>
      <Box flexDirection="row" alignItems="center" marginBottom={1}>
        <Text color={theme.colors.status.success} bold>
          ✔ Task Complete
        </Text>
      </Box>

      <Box flexDirection="column" marginBottom={1}>
        <Text color={theme.colors.text.bright} bold>
          {event.title}
        </Text>
        {event.description && (
          <Box marginTop={0}>
            <Text color={theme.colors.code.output}> {event.description}</Text>
          </Box>
        )}
      </Box>

      {event.filesCreated.length > 0 && (
        <Box flexDirection="column" paddingLeft={2} marginBottom={1}>
          <Text color={theme.colors.status.success} bold>
            Created:
          </Text>
          {event.filesCreated.map((file, idx) => (
            <Box key={idx} flexDirection="row">
              <Text color={theme.colors.text.muted}> </Text>
              <Text color={theme.colors.status.success}>+</Text>
              <Text color={theme.colors.text.bright}> {file}</Text>
            </Box>
          ))}
        </Box>
      )}

      {event.commandsExecuted.length > 0 && (
        <Box flexDirection="column" paddingLeft={2} marginBottom={1}>
          <Text color={theme.colors.status.info} bold>
            Executed:
          </Text>
          {event.commandsExecuted.map((cmd, idx) => (
            <Box key={idx} flexDirection="row">
              <Text color={theme.colors.text.muted}> </Text>
              <Text color={theme.colors.status.info}>$</Text>
              <Text color={theme.colors.text.bright}> {cmd}</Text>
            </Box>
          ))}
        </Box>
      )}

      {event.verified && event.verified.length > 0 && (
        <Box flexDirection="column" paddingLeft={2}>
          <Text color={theme.colors.status.success} bold>
            Verified:
          </Text>
          {event.verified.map((item, idx) => (
            <Box key={idx} flexDirection="row">
              <Text color={theme.colors.text.muted}> </Text>
              <Text color={theme.colors.status.success}>✔</Text>
              <Text color={theme.colors.text.bright}> {item}</Text>
            </Box>
          ))}
        </Box>
      )}
    </Box>
  );
});
