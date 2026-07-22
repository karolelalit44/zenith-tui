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
      {/* Command prompt header */}
      <Box flexDirection="row" alignItems="center" marginBottom={1} flexWrap="wrap">
        <Text color={theme.colors.status.info} bold>
          [EXEC]
        </Text>
        <Text color={theme.colors.text.muted}> </Text>
        <Text color={theme.colors.status.success} bold>
          ${' '}
        </Text>
        <Text color={theme.colors.text.bright} bold>
          {event.command}
        </Text>
        <Text color={theme.colors.text.muted}> ({(event.duration / 1000).toFixed(1)}s)</Text>
      </Box>

      {/* Terminal window execution container */}
      <Box
        flexDirection="column"
        width="100%"
        borderStyle="round"
        borderColor={theme.colors.code.border}
        paddingX={2}
        paddingY={1}
      >
        <Box flexDirection="row" justifyContent="space-between" alignItems="center" marginBottom={1}>
          <Text color={theme.colors.text.dim} bold>
            ❯ TERMINAL OUTPUT LOG
          </Text>
          <Text color={theme.colors.status.success} bold>
            [EXIT CODE 0]
          </Text>
        </Box>

        {event.output.length > 0 ? (
          event.output.map((line, idx) => (
            <Box key={idx} flexDirection="row">
              <Text color={theme.colors.text.dim}>│ </Text>
              <Text color={theme.colors.code.output} wrap="wrap">
                {line}
              </Text>
            </Box>
          ))
        ) : (
          <Text color={theme.colors.text.muted} italic>
            (command executed cleanly with zero stdout output)
          </Text>
        )}
      </Box>
    </Box>
  );
});
