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

  const cleanedOutput = event.output.map((line) => line.replace(/\r/g, '')).filter((line) => line.trim().length > 0);

  const width = Math.min(process.stdout.columns ?? 80, 80) - 4;

  return (
    <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
      {/* Command line */}
      <Box flexDirection="row" alignItems="center" marginBottom={0}>
        <Text color={isLive ? theme.colors.status.info : theme.colors.status.accent} bold>
          {isLive ? `[EXEC] ${ASCII_SPINNER_FRAMES[spinnerTick % 4]}` : '[RUN]'}
        </Text>
        <Text color={theme.colors.text.muted}> $ </Text>
        <Text color={theme.colors.text.bright} bold>
          {event.command}
        </Text>
      </Box>

      {/* Terminal window */}
      <Box flexDirection="column" width="100%">
        {/* Top border with label */}
        <Box flexDirection="row">
          <Text color={theme.colors.border.muted}>{'┌─'}</Text>
          <Text color={theme.colors.text.dim} bold>
            {' terminal '}
          </Text>
          <Text color={theme.colors.border.muted}>{'─'.repeat(Math.max(0, width - 14))}</Text>
          <Text color={theme.colors.border.muted}>{'┐'}</Text>
        </Box>

        {/* Output lines */}
        {cleanedOutput.length > 0 ? (
          cleanedOutput.map((line, idx) => (
            <Box key={idx} flexDirection="row" width="100%">
              <Text color={theme.colors.border.muted}>{'│'}</Text>
              <Text color={theme.colors.code.output} wrap="wrap">
                {' '}
                {line}
              </Text>
            </Box>
          ))
        ) : (
          <Box flexDirection="row" width="100%">
            <Text color={theme.colors.border.muted}>{'│'}</Text>
            <Text color={theme.colors.text.muted} italic>
              {'  (no output)'}
            </Text>
          </Box>
        )}

        {/* Exit status + bottom border */}
        <Box flexDirection="row" width="100%">
          <Text color={theme.colors.border.muted}>{'├─'}</Text>
          <Text color={isLive ? theme.colors.status.info : theme.colors.status.success} bold>
            {isLive ? ' running ' : ` exit ${event.command.includes('&&') ? '(chained)' : '0'} `}
          </Text>
          <Text color={theme.colors.text.dim}>{(event.duration / 1000).toFixed(1)}s</Text>
          <Text color={theme.colors.border.muted}>{'─'.repeat(Math.max(0, width - 20))}</Text>
          <Text color={theme.colors.border.muted}>{'┘'}</Text>
        </Box>
      </Box>
    </Box>
  );
});
