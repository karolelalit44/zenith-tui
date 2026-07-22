import { Box, Text } from 'ink';
import React from 'react';
import { useTickAnimation } from '../../../hooks/useTickAnimation';
import { useTheme } from '../../../theme/ThemeContext';
import type { ProgressEvent } from '../../../types/scenario';

interface ProgressBarProps {
  event: ProgressEvent;
}

export const ProgressBar: React.FC<ProgressBarProps> = ({ event }) => {
  const { theme } = useTheme();
  const tick = useTickAnimation(200);

  const spinners = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'];
  const activeIdx = event.steps.findIndex((s) => s.status === 'active');
  const doneCount = event.steps.filter((s) => s.status === 'done').length;
  const progress = event.steps.length > 0 ? doneCount / event.steps.length : 0;
  const barWidth = 20;
  const filled = Math.round(barWidth * progress);
  const bar = '█'.repeat(filled) + '░'.repeat(barWidth - filled);

  return (
    <Box flexDirection="column" marginBottom={1} paddingX={1}>
      <Box flexDirection="row" alignItems="center" marginBottom={1}>
        <Text color={theme.colors.text.emerald} bold>
          ◆ {event.label}
        </Text>
        <Text color={theme.colors.text.muted}> </Text>
        <Text color={theme.colors.text.muted}>{bar}</Text>
        <Text color={theme.colors.text.muted}> </Text>
        <Text color={theme.colors.text.emerald} bold>
          {Math.round(progress * 100)}%
        </Text>
      </Box>

      <Box flexDirection="column" paddingLeft={2}>
        {event.steps.map((step, idx) => {
          let icon: string;
          let color: string;
          switch (step.status) {
            case 'done':
              icon = '✔';
              color = theme.colors.text.emerald;
              break;
            case 'active':
              icon = spinners[tick % spinners.length];
              color = theme.colors.text.ethereal;
              break;
            case 'error':
              icon = '✗';
              color = theme.colors.text.error;
              break;
            default:
              icon = '○';
              color = theme.colors.text.muted;
              break;
          }
          return (
            <Box key={idx} flexDirection="row" alignItems="center">
              <Box width={2}>
                <Text color={color}>{icon}</Text>
              </Box>
              <Text color={idx === activeIdx ? theme.colors.text.ethereal : theme.colors.text.muted}>{step.label}</Text>
            </Box>
          );
        })}
      </Box>
    </Box>
  );
};
