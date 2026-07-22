import React from 'react';
import { Box, Text } from 'ink';
import { useTheme } from '../../../theme/ThemeContext';
import { PlannerActionPanelEvent } from '../../../types/scenario';

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

      <Box flexDirection="column" paddingX={2} paddingY={1} borderStyle="round" borderColor="#3FB950">
        <Box flexDirection="row" alignItems="center" marginBottom={1}>
          <Text color="#3FB950" bold>✔ Plan Ready</Text>
        </Box>

        <Box flexDirection="row" alignItems="center" marginBottom={1}>
          <Text color="#E6EDF3" bold>Press </Text>
          <Text color="#58A6FF" bold underline>Ctrl + S</Text>
          <Text color="#E6EDF3" bold> to save this plan.</Text>
        </Box>

        <Box flexDirection="row" alignItems="center">
          <Text color="#8B949E">The plan will be exported as: </Text>
          <Text color="#58A6FF" bold>{event.defaultFilename || 'zenith_plans/implementation-plan.md'}</Text>
        </Box>

        {event.saved && (
          <Box marginTop={1} flexDirection="row" alignItems="center">
            <Text color="#3FB950" bold>[SAVED SUCCESS] </Text>
            <Text color="#E6EDF3">File written to {event.defaultFilename}</Text>
          </Box>
        )}
      </Box>

      <Box width="100%">
        <Text color={theme.colors.border.active}>─────────────────────────────────────────────────────────────</Text>
      </Box>
    </Box>
  );
});
