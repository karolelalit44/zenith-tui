import React from 'react';
import { Box, Text } from 'ink';
import { useTheme } from '../../../theme/ThemeContext';
import { ModeMismatchEvent } from '../../../types/scenario';

interface ModeMismatchViewProps {
  event: ModeMismatchEvent;
}

export const ModeMismatchView: React.FC<ModeMismatchViewProps> = React.memo(({ event }) => {
  const { theme } = useTheme();

  return (
    <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
      <Box flexDirection="column" width="100%" borderStyle="round" borderColor="#D29922" paddingX={1} paddingY={1}>
        <Box flexDirection="row" alignItems="center" marginBottom={1}>
          <Text color="#D29922" bold>[MODE MISMATCH] </Text>
          <Text color="#E6EDF3" bold>Cannot fulfill request in current [{event.currentMode.toUpperCase()}] mode</Text>
        </Box>

        <Box flexDirection="row" marginBottom={1}>
          <Text color="#8B949E">Reason: </Text>
          <Text color="#E6EDF3">{event.reason}</Text>
        </Box>

        <Box flexDirection="row" marginBottom={1}>
          <Text color="#8B949E">Active Mode: </Text>
          <Text color="#BD93F9" bold>[{event.currentMode.toUpperCase()}] </Text>
          <Text color="#8B949E">→ Suggested Mode: </Text>
          <Text color="#3FB950" bold>[{event.suggestedMode.toUpperCase()}]</Text>
        </Box>

        <Box flexDirection="row" alignItems="center" marginTop={1} paddingX={1} backgroundColor="#21262D">
          <Text color="#58A6FF" bold>Action Required: </Text>
          <Text color="#E6EDF3">Type </Text>
          <Text color="#3FB950" bold underline>/mode {event.suggestedMode}</Text>
          <Text color="#E6EDF3"> or press </Text>
          <Text color="#58A6FF" bold>Shift + M</Text>
          <Text color="#E6EDF3"> to switch mode.</Text>
        </Box>
      </Box>
    </Box>
  );
});
