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
    <Box
      flexDirection="column"
      width="100%"
      borderStyle="round"
      borderColor={theme.colors.status.success}
      paddingX={1}
      paddingY={1}
      marginBottom={1}
    >
      <Box flexDirection="row" alignItems="center" marginBottom={0}>
        <Text color={theme.colors.status.success} bold>
          [SUCCESS]
        </Text>
        <Text color={theme.colors.text.muted}> </Text>
        <Text color={theme.colors.text.ethereal}>{event.message}</Text>
      </Box>

      {event.tool && (
        <Box flexDirection="row" paddingLeft={1} marginTop={0}>
          <Text color={theme.colors.text.muted}>Tool: </Text>
          <Text color={theme.colors.text.bright}>{event.tool}</Text>
        </Box>
      )}

      {event.result && (
        <Box flexDirection="column" paddingLeft={1} marginTop={0}>
          {event.result.output && (
            <Box flexDirection="row">
              <Text color={theme.colors.text.muted}>Output: </Text>
              <Text color={theme.colors.text.bright} wrap="wrap">
                {event.result.output}
              </Text>
            </Box>
          )}
          {event.result.error && (
            <Box flexDirection="row">
              <Text color={theme.colors.status.error}>Error: </Text>
              <Text color={theme.colors.text.bright} wrap="wrap">
                {event.result.error}
              </Text>
            </Box>
          )}
        </Box>
      )}

      {event.filesCreated.length > 0 && (
        <Box flexDirection="column" paddingLeft={1} marginTop={0}>
          <Text color={theme.colors.text.muted}>Files created:</Text>
          {event.filesCreated.map((file, idx) => (
            <Box key={idx} flexDirection="row">
              <Text color={theme.colors.status.success}>+ </Text>
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

      {event.iterations !== undefined && (
        <Box flexDirection="row" paddingLeft={1} marginTop={0}>
          <Text color={theme.colors.text.muted}>Iterations: </Text>
          <Text color={theme.colors.text.bright}>{event.iterations}</Text>
        </Box>
      )}

      {event.tokenInfo && (
        <Box flexDirection="row" paddingLeft={1} marginTop={0}>
          <Text color={theme.colors.text.muted}>Tokens: </Text>
          <Text color={theme.colors.text.bright}>
            {event.tokenInfo.used}/{event.tokenInfo.total} ({Math.round(event.tokenInfo.percent * 100)}%)
          </Text>
        </Box>
      )}
    </Box>
  );
});
