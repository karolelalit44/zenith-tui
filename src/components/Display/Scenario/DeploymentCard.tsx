import React, { useState, useEffect } from 'react';
import { Box, Text } from 'ink';
import { useTheme } from '../../../theme/ThemeContext';
import { DeploymentEvent } from '../../../types/scenario';

interface DeploymentCardProps {
  event: DeploymentEvent;
}

export const DeploymentCard: React.FC<DeploymentCardProps> = ({ event }) => {
  const { theme } = useTheme();
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (event.status === 'deploying') {
      const interval = setInterval(() => setTick(t => t + 1), 200);
      return () => clearInterval(interval);
    }
  }, [event.status]);

  const spinners = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'];

  let icon: string;
  let color: string;
  switch (event.status) {
    case 'success':
      icon = '✔';
      color = theme.colors.text.emerald;
      break;
    case 'deploying':
      icon = spinners[tick % spinners.length];
      color = theme.colors.text.ethereal;
      break;
    case 'failed':
      icon = '✗';
      color = theme.colors.text.error;
      break;
    default:
      icon = '○';
      color = theme.colors.text.muted;
      break;
  }

  return (
    <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
      <Box flexDirection="row" alignItems="center" marginBottom={1} flexWrap="wrap">
        <Text color="#3FB950" bold>[DEPLOY]</Text>
        <Text color={theme.colors.text.muted}> → </Text>
        <Text color="#E6EDF3" bold>{event.target}</Text>
      </Box>

      <Box flexDirection="row" alignItems="center" paddingLeft={2}>
        <Box width={2}>
          <Text color={color}>{icon}</Text>
        </Box>
        <Text color={color} bold>{event.status === 'deploying' ? 'Deploying...' : event.status === 'success' ? 'Deployed' : 'Failed'}</Text>
        {event.url && (
          <Text color={theme.colors.text.muted}> → </Text>
        )}
        {event.url && (
          <Text color={theme.colors.text.emerald} underline>{event.url}</Text>
        )}
      </Box>

      {event.output && event.output.length > 0 && (
        <Box flexDirection="column" paddingLeft={2} marginTop={1}>
          {event.output.map((line, idx) => (
            <Text key={idx} color={theme.colors.text.muted}>{line}</Text>
          ))}
        </Box>
      )}
    </Box>
  );
};
