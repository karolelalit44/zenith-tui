import { Box, Text } from 'ink';
import React from 'react';
import { useTheme } from '../../../theme/ThemeContext';
import type { ScenarioEvent } from '../../../types/scenario';

interface UnknownEventFallbackProps {
  event: ScenarioEvent;
}

export const UnknownEventFallback: React.FC<UnknownEventFallbackProps> = ({ event }) => {
  const { theme } = useTheme();
  const eventKind = event.kind ? String(event.kind).toUpperCase() : 'EVENT';

  return (
    <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
      <Box flexDirection="row" alignItems="center" marginBottom={1}>
        <Text color={theme.colors.status.warning} bold>
          [{eventKind}]
        </Text>
        <Text color={theme.colors.text.muted}> </Text>
        <Text color={theme.colors.text.bright}>Generic Event Payload</Text>
      </Box>

      <Box
        flexDirection="column"
        width="100%"
        borderStyle="round"
        borderColor={theme.colors.status.warning}
        paddingX={2}
        paddingY={1}
      >
        <Box marginBottom={1}>
          <Text color={theme.colors.text.muted} italic>
            No specific UI renderer registered for kind: &quot;{event.kind}&quot;. Fallback raw data render:
          </Text>
        </Box>

        {Object.entries(event)
          .filter(([key]) => key !== 'id' && key !== 'kind')
          .map(([key, val], idx) => (
            <Box key={idx} flexDirection="row" marginBottom={0}>
              <Text color={theme.colors.status.info} bold>
                {key}:{' '}
              </Text>
              <Text color={theme.colors.text.ethereal}>
                {typeof val === 'object' ? JSON.stringify(val) : String(val)}
              </Text>
            </Box>
          ))}
      </Box>
    </Box>
  );
};
