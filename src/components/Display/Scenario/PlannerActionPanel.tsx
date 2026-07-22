import { Box, Text } from 'ink';
import React from 'react';
import { useTheme } from '../../../theme/ThemeContext';
import type { PlannerActionPanelEvent } from '../../../types/scenario';

interface PlannerActionPanelProps {
  event: PlannerActionPanelEvent;
}

export const PlannerActionPanel: React.FC<PlannerActionPanelProps> = React.memo(({ event }) => {
  const { theme } = useTheme();

  return (
    <Box flexDirection="column" width="100%" marginTop={1} marginBottom={1} paddingX={1}>
      <Box width="100%">
        <Text color={theme.colors.border.active}>─────────────────────────────────────────────────────────────</Text>
      </Box>

      <Box
        flexDirection="column"
        paddingX={2}
        paddingY={1}
        borderStyle="round"
        borderColor={theme.colors.status.success}
      >
        <Box flexDirection="row" alignItems="center" marginBottom={1}>
          <Text color={theme.colors.status.success} bold>
            ✔ Plan Ready
          </Text>
        </Box>

        <Box flexDirection="row" alignItems="center" marginBottom={1}>
          <Text color={theme.colors.text.bright} bold>
            Press{' '}
          </Text>
          <Text color={theme.colors.status.info} bold underline>
            Ctrl + S
          </Text>
          <Text color={theme.colors.text.bright} bold>
            {' '}
            to save this plan.
          </Text>
        </Box>

        <Box flexDirection="row" alignItems="center">
          <Text color={theme.colors.text.muted}>The plan will be exported as: </Text>
          <Text color={theme.colors.status.info} bold>
            {event.defaultFilename || 'zenith_plans/implementation-plan.md'}
          </Text>
        </Box>

        {event.saved && (
          <Box marginTop={1} flexDirection="row" alignItems="center">
            <Text color={theme.colors.status.success} bold>
              [SAVED SUCCESS]{' '}
            </Text>
            <Text color={theme.colors.text.bright}>File written to {event.defaultFilename}</Text>
          </Box>
        )}
      </Box>

      <Box width="100%">
        <Text color={theme.colors.border.active}>─────────────────────────────────────────────────────────────</Text>
      </Box>
    </Box>
  );
});
