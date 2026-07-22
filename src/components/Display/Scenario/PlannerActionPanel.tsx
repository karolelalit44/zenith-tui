import { Box, Text } from 'ink';
import React from 'react';
import { useTheme } from '../../../theme/ThemeContext';
import type { PlannerActionPanelEvent } from '../../../types/scenario';

interface PlannerActionPanelProps {
  event: PlannerActionPanelEvent;
}

export const PlannerActionPanel: React.FC<PlannerActionPanelProps> = React.memo(({ event }) => {
  const { theme } = useTheme();
  const exportPath = event.defaultFilename?.includes('/')
    ? event.defaultFilename
    : `zenith_plans/${event.defaultFilename || 'implementation-plan.md'}`;

  return (
    <Box flexDirection="column" width="100%" marginTop={1} marginBottom={1} paddingX={1}>
      <Box
        flexDirection="column"
        width="100%"
        paddingX={2}
        paddingY={1}
        borderStyle="round"
        borderColor={theme.colors.status.success}
      >
        <Box flexDirection="row" alignItems="center" marginBottom={1}>
          <Text color={theme.colors.status.success} bold>
            [PLAN EXPORT READY]
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
            to export implementation plan to file system.
          </Text>
        </Box>

        <Box flexDirection="row" alignItems="center">
          <Text color={theme.colors.text.muted}>Target path: </Text>
          <Text color={theme.colors.status.info} bold>
            {exportPath}
          </Text>
        </Box>

        {event.saved && (
          <Box marginTop={1} flexDirection="row" alignItems="center">
            <Text color={theme.colors.status.success} bold>
              [SAVED SUCCESS]{' '}
            </Text>
            <Text color={theme.colors.text.bright}>Plan file written to {exportPath}</Text>
          </Box>
        )}
      </Box>
    </Box>
  );
});
