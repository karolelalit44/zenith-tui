import { Box, Text } from 'ink';
import React from 'react';
import { useTickAnimation } from '../../../hooks/useTickAnimation';
import { useTheme } from '../../../theme/ThemeContext';
import type { DeploymentEvent } from '../../../types/scenario';

interface DeploymentCardProps {
  event: DeploymentEvent;
}

const SPINNERS = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'];

export const DeploymentCard: React.FC<DeploymentCardProps> = ({ event }) => {
  const { theme } = useTheme();
  const tick = useTickAnimation(200, event.status === 'deploying');

  let icon: string;
  let color: string;
  switch (event.status) {
    case 'success':
      icon = '✔';
      color = theme.colors.status.success;
      break;
    case 'deploying':
      icon = SPINNERS[tick % SPINNERS.length];
      color = theme.colors.status.info;
      break;
    case 'failed':
      icon = '✗';
      color = theme.colors.status.error;
      break;
    default:
      icon = '○';
      color = theme.colors.text.muted;
      break;
  }

  return (
    <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
      <Box flexDirection="row" alignItems="center" marginBottom={1} flexWrap="wrap">
        <Text color={theme.colors.status.success} bold>
          [DEPLOY]
        </Text>
        <Text color={theme.colors.text.muted}> → </Text>
        <Text color={theme.colors.text.bright} bold>
          {event.target}
        </Text>
      </Box>

      <Box flexDirection="row" alignItems="center" paddingLeft={2}>
        <Box width={2}>
          <Text color={color}>{icon}</Text>
        </Box>
        <Text color={color} bold>
          {event.status === 'deploying' ? 'Deploying...' : event.status === 'success' ? 'Deployed' : 'Failed'}
        </Text>
        {event.url && (
          <>
            <Text color={theme.colors.text.muted}> → </Text>
            <Text color={theme.colors.status.success} underline>
              {event.url}
            </Text>
          </>
        )}
      </Box>

      {event.output && event.output.length > 0 && (
        <Box flexDirection="column" paddingLeft={2} marginTop={1}>
          {event.output.map((line, idx) => (
            <Text key={idx} color={theme.colors.text.muted}>
              {line}
            </Text>
          ))}
        </Box>
      )}
    </Box>
  );
};
