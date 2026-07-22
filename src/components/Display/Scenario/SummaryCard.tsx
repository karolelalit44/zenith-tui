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
    <Box flexDirection="column" width="100%" marginTop={1} marginBottom={1} paddingX={1}>
      {/* Summary Header */}
      <Box flexDirection="row" alignItems="center" marginBottom={1}>
        <Text color={theme.colors.status.success} bold>
          [SUMMARY]
        </Text>
        <Text color={theme.colors.text.muted}> </Text>
        <Text color={theme.colors.text.bright} bold>
          {event.title}
        </Text>
      </Box>

      {/* Summary Box Container */}
      <Box
        flexDirection="column"
        width="100%"
        borderStyle="round"
        borderColor={theme.colors.status.success}
        paddingX={2}
        paddingY={1}
      >
        {event.description && (
          <Box marginBottom={1}>
            <Text color={theme.colors.text.ethereal}>{event.description}</Text>
          </Box>
        )}

        {event.filesCreated.length > 0 && (
          <Box flexDirection="column" marginBottom={1}>
            <Text color={theme.colors.status.success} bold>
              [FILES CREATED]
            </Text>
            <Box flexDirection="column" paddingLeft={2}>
              {event.filesCreated.map((file, idx) => (
                <Box key={idx} flexDirection="row">
                  <Text color={theme.colors.status.success}>+ </Text>
                  <Text color={theme.colors.text.bright}>{file}</Text>
                </Box>
              ))}
            </Box>
          </Box>
        )}

        {event.commandsExecuted.length > 0 && (
          <Box flexDirection="column" marginBottom={1}>
            <Text color={theme.colors.status.info} bold>
              [COMMANDS EXECUTED]
            </Text>
            <Box flexDirection="column" paddingLeft={2}>
              {event.commandsExecuted.map((cmd, idx) => (
                <Box key={idx} flexDirection="row">
                  <Text color={theme.colors.status.info}>$ </Text>
                  <Text color={theme.colors.text.bright}>{cmd}</Text>
                </Box>
              ))}
            </Box>
          </Box>
        )}

        {event.verified && event.verified.length > 0 && (
          <Box flexDirection="column">
            <Text color={theme.colors.status.success} bold>
              [VERIFICATIONS PASSED]
            </Text>
            <Box flexDirection="column" paddingLeft={2}>
              {event.verified.map((item, idx) => (
                <Box key={idx} flexDirection="row">
                  <Text color={theme.colors.status.success}>✔ </Text>
                  <Text color={theme.colors.text.ethereal}>{item}</Text>
                </Box>
              ))}
            </Box>
          </Box>
        )}
      </Box>
    </Box>
  );
});
