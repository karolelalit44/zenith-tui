import { Box, Text } from 'ink';
import React from 'react';
import { SPINNER_FRAMES } from '../../../constants/animation';
import { useAnimationTick } from '../../../context/AnimationContext';
import { useTheme } from '../../../theme/ThemeContext';
import type { ProgressEvent } from '../../../types/scenario';

interface ProgressBarProps {
  event: ProgressEvent;
}

export const ProgressBar: React.FC<ProgressBarProps> = React.memo(({ event }) => {
  const { theme } = useTheme();
  const tick = useAnimationTick();

  const barWidth = 20;

  let progress: number;
  if (typeof event.percent === 'number') {
    progress = event.percent / 100;
  } else if (event.steps.length > 0) {
    const doneCount = event.steps.filter((s) => s.status === 'done').length;
    progress = doneCount / event.steps.length;
  } else {
    progress = 0;
  }

  const filled = Math.round(barWidth * progress);

  return (
    <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
      <Box flexDirection="row" alignItems="center" marginBottom={1}>
        <Text color={theme.colors.status.warning} bold>
          * {event.label}
        </Text>
        <Text color={theme.colors.text.muted}> </Text>
        <Text color={theme.colors.status.success}>{'\u2588'.repeat(filled)}</Text>
        <Text color={theme.colors.text.muted}>{'\u2591'.repeat(barWidth - filled)}</Text>
        <Text color={theme.colors.text.muted}> </Text>
        <Text color={theme.colors.text.bright} bold>
          {Math.round(progress * 100)}%
        </Text>
        {event.iteration !== undefined && (
          <>
            <Text color={theme.colors.text.muted}> </Text>
            <Text color={theme.colors.text.dim}>(iter {event.iteration})</Text>
          </>
        )}
      </Box>

      {event.steps.length > 0 && (
        <Box flexDirection="column" paddingLeft={1}>
          {event.steps.map((step, idx) => {
            let icon: string;
            let color: string;
            let textColor: string;
            switch (step.status) {
              case 'done':
                icon = '✓';
                color = theme.colors.status.success;
                textColor = theme.colors.text.bright;
                break;
              case 'active':
                icon = SPINNER_FRAMES[tick % SPINNER_FRAMES.length];
                color = theme.colors.text.ethereal;
                textColor = theme.colors.text.bright;
                break;
              case 'error':
                icon = '✗';
                color = theme.colors.status.error;
                textColor = theme.colors.text.error;
                break;
              default:
                icon = '·';
                color = theme.colors.text.dim;
                textColor = theme.colors.text.muted;
                break;
            }
            return (
              <Box key={idx} flexDirection="row" alignItems="center">
                <Box width={2}>
                  <Text color={color}>{icon}</Text>
                </Box>
                <Text color={textColor}>{step.label}</Text>
              </Box>
            );
          })}
        </Box>
      )}
    </Box>
  );
});
