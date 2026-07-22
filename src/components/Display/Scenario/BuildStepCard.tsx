import { Box, Text } from 'ink';
import React from 'react';
import { useTickAnimation } from '../../../hooks/useTickAnimation';
import { useTheme } from '../../../theme/ThemeContext';
import type { BuildStepEvent } from '../../../types/scenario';

interface BuildStepCardProps {
  event: BuildStepEvent;
}

const SPINNERS = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'];

export const BuildStepCard: React.FC<BuildStepCardProps> = React.memo(({ event }) => {
  const { theme } = useTheme();
  const tick = useTickAnimation(150, event.status === 'running');

  let icon: string;
  let color: string;
  switch (event.status) {
    case 'success':
      icon = '✔';
      color = theme.colors.status.success;
      break;
    case 'running':
      icon = SPINNERS[tick % SPINNERS.length];
      color = theme.colors.status.info;
      break;
    case 'error':
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
      {/* Header */}
      <Box flexDirection="row" alignItems="center" marginBottom={1} flexWrap="wrap">
        <Text color={theme.colors.status.info} bold>
          [BUILD STEP]
        </Text>
        <Text color={theme.colors.text.muted}> </Text>
        <Text color={color} bold>
          {icon}
        </Text>
        <Text color={theme.colors.text.muted}> </Text>
        <Text color={theme.colors.text.bright} bold>
          {event.step}
        </Text>
        {event.duration !== undefined && (
          <Text color={theme.colors.text.muted}> ({(event.duration / 1000).toFixed(1)}s)</Text>
        )}
      </Box>

      {/* Output log */}
      {event.output && event.output.length > 0 && (
        <Box
          flexDirection="column"
          width="100%"
          borderStyle="round"
          borderColor={theme.colors.code.border}
          paddingX={2}
          paddingY={1}
        >
          {event.output.map((line, idx) => (
            <Box key={idx} flexDirection="row">
              <Text color={theme.colors.text.dim}>│ </Text>
              <Text color={theme.colors.code.output} wrap="wrap">
                {line}
              </Text>
            </Box>
          ))}
        </Box>
      )}
    </Box>
  );
});
