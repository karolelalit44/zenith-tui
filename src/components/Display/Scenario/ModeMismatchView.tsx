import { Box, Text } from 'ink';
import React from 'react';
import { useTheme } from '../../../theme/ThemeContext';
import type { ModeMismatchEvent } from '../../../types/scenario';

interface ModeMismatchViewProps {
  event: ModeMismatchEvent;
}

export const ModeMismatchView: React.FC<ModeMismatchViewProps> = React.memo(({ event }) => {
  const { theme } = useTheme();

  return (
    <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
      <Box
        flexDirection="column"
        width="100%"
        borderStyle="round"
        borderColor={theme.colors.status.warning}
        paddingX={1}
        paddingY={1}
      >
        <Box flexDirection="row" alignItems="center" marginBottom={1}>
          <Text color={theme.colors.status.warning} bold>
            [MODE MISMATCH]{' '}
          </Text>
          <Text color={theme.colors.text.bright} bold>
            Cannot fulfill request in current [{event.currentMode.toUpperCase()}] mode
          </Text>
        </Box>

        <Box flexDirection="row" marginBottom={1}>
          <Text color={theme.colors.text.muted}>Reason: </Text>
          <Text color={theme.colors.text.bright}>{event.reason}</Text>
        </Box>

        <Box flexDirection="row" marginBottom={1}>
          <Text color={theme.colors.text.muted}>Active Mode: </Text>
          <Text color={theme.colors.status.accent} bold>
            [{event.currentMode.toUpperCase()}]{' '}
          </Text>
          <Text color={theme.colors.text.muted}>→ Suggested Mode: </Text>
          <Text color={theme.colors.status.success} bold>
            [{event.suggestedMode.toUpperCase()}]
          </Text>
        </Box>

        <Box flexDirection="row" alignItems="center" marginTop={1} paddingX={1} backgroundColor={theme.colors.bg.modal}>
          <Text color={theme.colors.status.info} bold>
            Action Required:{' '}
          </Text>
          <Text color={theme.colors.text.bright}>Type </Text>
          <Text color={theme.colors.status.success} bold underline>
            /mode {event.suggestedMode}
          </Text>
          <Text color={theme.colors.text.bright}> or press </Text>
          <Text color={theme.colors.status.info} bold>
            Shift + M
          </Text>
          <Text color={theme.colors.text.bright}> to switch mode.</Text>
        </Box>
      </Box>
    </Box>
  );
});
