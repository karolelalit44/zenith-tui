import { Box, Text } from 'ink';
import React from 'react';
import { ASCII_SPINNER_FRAMES } from '../../../constants/animation';
import { useTickAnimation } from '../../../hooks/useTickAnimation';
import { useTheme } from '../../../theme/ThemeContext';
import type { TerminalEvent } from '../../../types/scenario';
import type { EventRenderContext } from './componentRegistry';

interface TerminalBlockProps {
  event: TerminalEvent;
  context?: EventRenderContext;
}

export const TerminalBlock: React.FC<TerminalBlockProps> = React.memo(({ event, context }) => {
  const { theme } = useTheme();
  const spinnerTick = useTickAnimation(100);
  const isLive = context?.isRunning && !context?.isHistorical;

  const cleanedOutput = event.output
    .map((line) => line.replace(/\r/g, ''))
    .filter((line) => line.trim().length > 0);

  return (
    <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
      {/* Command prompt header */}
      <Box flexDirection="row" alignItems="center" marginBottom={1} flexWrap="wrap">
        <Text color={isLive ? theme.colors.status.info : theme.colors.status.accent} bold>
          {isLive ? `[EXECUTING COMMAND] ${ASCII_SPINNER_FRAMES[spinnerTick % 4]}` : '[RUN]'}
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
        borderStyle="single"
        borderColor={theme.colors.border.muted}
        paddingX={1}
        paddingY={0}
      >
        <Box flexDirection="row" justifyContent="space-between" alignItems="center" marginBottom={0}>
          <Text color={theme.colors.text.dim} bold>
            [TERMINAL OUTPUT]
          </Text>
          <Text color={isLive ? theme.colors.status.info : theme.colors.status.success} bold>
            {isLive ? '[RUNNING]' : '[EXIT 0]'}
          </Text>
        </Box>

        {cleanedOutput.length > 0 ? (
          cleanedOutput.map((line, idx) => (
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
