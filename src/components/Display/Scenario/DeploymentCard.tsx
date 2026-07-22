import { Box, Text } from 'ink';
import React from 'react';
import { SPINNER_FRAMES } from '../../../constants/animation';
import { useTickAnimation } from '../../../hooks/useTickAnimation';
import { useTheme } from '../../../theme/ThemeContext';
import type { DeploymentEvent } from '../../../types/scenario';

interface DeploymentCardProps {
  event: DeploymentEvent;
}

export const DeploymentCard: React.FC<DeploymentCardProps> = React.memo(({ event }) => {
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
      icon = SPINNER_FRAMES[tick % SPINNER_FRAMES.length];
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
      {/* Deployment Header */}
      <Box flexDirection="row" alignItems="center" marginBottom={1} flexWrap="wrap">
        <Text color={theme.colors.status.success} bold>
          [DEPLOYMENT]
        </Text>
        <Text color={theme.colors.text.muted}> → </Text>
        <Text color={theme.colors.text.bright} bold>
          {event.target}
        </Text>
      </Box>

      {/* Deployment Status Container */}
      <Box flexDirection="column" width="100%" borderStyle="round" borderColor={color} paddingX={2} paddingY={1}>
        <Box flexDirection="row" alignItems="center">
          <Box width={2}>
            <Text color={color} bold>
              {icon}
            </Text>
          </Box>
          <Text color={color} bold>
            {event.status === 'deploying'
              ? 'Deploying Build Artifact...'
              : event.status === 'success'
                ? 'Deployed Successfully'
                : 'Deployment Failed'}
          </Text>
          {event.url && (
            <>
              <Text color={theme.colors.text.muted}> → </Text>
              <Text color={theme.colors.status.success} bold underline>
                {event.url}
              </Text>
            </>
          )}
        </Box>

        {event.output && event.output.length > 0 && (
          <Box flexDirection="column" marginTop={1}>
            {event.output.map((line, idx) => (
              <Box key={idx} flexDirection="row">
                <Text color={theme.colors.text.dim}>│ </Text>
                <Text color={theme.colors.text.muted} wrap="wrap">
                  {line}
                </Text>
              </Box>
            ))}
          </Box>
        )}
      </Box>
    </Box>
  );
});
