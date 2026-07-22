import { Box, Text } from 'ink';
import React from 'react';
import { useTheme } from '../../../theme/ThemeContext';
import type { TerminalEvent } from '../../../types/scenario';

interface TerminalBlockProps {
  event: TerminalEvent;
}

export const TerminalBlock: React.FC<TerminalBlockProps> = React.memo(({ event }) => {
  const { theme } = useTheme();

  return (
    <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
      <Box flexDirection="row" alignItems="center" marginBottom={1} flexWrap="wrap">
        <Text color={theme.colors.status.info} bold>
          [COMMAND PROMPT]
        </Text>
        <Text color={theme.colors.text.muted}> </Text>
        <Text color={theme.colors.status.info} bold>
          ${' '}
        </Text>
        <Text color={theme.colors.text.bright} bold>
          {event.command}
        </Text>
        <Text color={theme.colors.text.muted}> ({(event.duration / 1000).toFixed(1)}s)</Text>
      </Box>

      <Box flexDirection="column" width="100%" borderStyle="round" borderColor={theme.colors.code.border} paddingX={1}>
        {event.output.length > 0 ? (
          event.output.map((line, idx) => (
            <Text key={idx} color={theme.colors.code.output} wrap="wrap">
              {line}
            </Text>
          ))
        ) : (
          <Text color={theme.colors.text.muted}>(command executed silently)</Text>
        )}

        <Box marginTop={1} flexDirection="row" justifyContent="flex-end">
          <Text color={theme.colors.status.success} bold>
            [EXIT CODE 0]
          </Text>
        </Box>
      </Box>
    </Box>
  );
});
