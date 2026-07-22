import React from 'react';
import { Box, Text } from 'ink';
import { useTheme } from '../../../theme/ThemeContext';
import { SummaryEvent } from '../../../types/scenario';

interface SummaryCardProps {
  event: SummaryEvent;
}

export const SummaryCard: React.FC<SummaryCardProps> = React.memo(({ event }) => {
  const { theme } = useTheme();

  return (
    <Box flexDirection="column" marginTop={1} marginBottom={1} paddingX={1}>
      <Box flexDirection="row" alignItems="center" marginBottom={1}>
        <Text color="#3FB950" bold>✔ Task Complete</Text>
      </Box>

      <Box flexDirection="column" marginBottom={1}>
        <Text color="#E6EDF3" bold>{event.title}</Text>
        {event.description && (
          <Box marginTop={0}>
            <Text color="#C9D1D9">  {event.description}</Text>
          </Box>
        )}
      </Box>

      {event.filesCreated.length > 0 && (
        <Box flexDirection="column" paddingLeft={2} marginBottom={1}>
          <Text color="#3FB950" bold>Created:</Text>
          {event.filesCreated.map((file, idx) => (
            <Box key={idx} flexDirection="row">
              <Text color="#8B949E">  </Text>
              <Text color="#3FB950">+</Text>
              <Text color="#E6EDF3"> {file}</Text>
            </Box>
          ))}
        </Box>
      )}

      {event.commandsExecuted.length > 0 && (
        <Box flexDirection="column" paddingLeft={2} marginBottom={1}>
          <Text color="#58A6FF" bold>Executed:</Text>
          {event.commandsExecuted.map((cmd, idx) => (
            <Box key={idx} flexDirection="row">
              <Text color="#8B949E">  </Text>
              <Text color="#58A6FF">$</Text>
              <Text color="#E6EDF3"> {cmd}</Text>
            </Box>
          ))}
        </Box>
      )}

      {event.verified && event.verified.length > 0 && (
        <Box flexDirection="column" paddingLeft={2}>
          <Text color="#3FB950" bold>Verified:</Text>
          {event.verified.map((item, idx) => (
            <Box key={idx} flexDirection="row">
              <Text color="#8B949E">  </Text>
              <Text color="#3FB950">✔</Text>
              <Text color="#E6EDF3"> {item}</Text>
            </Box>
          ))}
        </Box>
      )}
    </Box>
  );
});
