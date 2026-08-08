import { Box, Text } from 'ink';
import React from 'react';
import { useTheme } from '../../../theme/ThemeContext';
import type { ScenarioEvent } from '../../../types/scenario';

interface ContextStatusBlockProps {
  event: ScenarioEvent;
}

/**
 * Subtle one-line status for context-compaction lifecycle events.
 * These are informational (not errors/warnings), so they render dimly
 * instead of as a loud warning banner.
 */
export const ContextStatusBlock: React.FC<ContextStatusBlockProps> = React.memo(({ event }) => {
  const { theme } = useTheme();
  const message = 'message' in event && typeof event.message === 'string' ? event.message : '';

  return (
    <Box flexDirection="row" width="100%" marginBottom={1} paddingX={1}>
      <Text color={theme.colors.text.dim}>⊡ </Text>
      <Text color={theme.colors.text.dim} wrap="wrap">
        {message}
      </Text>
    </Box>
  );
});
