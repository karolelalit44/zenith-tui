import { Box, Text } from 'ink';
import React from 'react';
import { SPINNER_FRAMES } from '../../../constants/animation';
import { useAnimationTick } from '../../../context/AnimationContext';
import { useTheme } from '../../../theme/ThemeContext';
import type { ProgressEvent } from '../../../types/scenario';

interface ProgressBarProps {
  event: ProgressEvent;
}

/**
 * Compact live activity row for agent tool execution.
 *
 * One line: current-step status icon + label, with a dim done/total counter.
 * The old design (big percent bar + full checklist) stacked visual noise on
 * every snapshot; all the information a user needs while a turn runs is
 * WHAT is running right now and HOW MUCH is left.
 *
 * Rows that merely echo an in-flight tool (same command the terminal window
 * card already shows) are suppressed upstream — see
 * `progressDuplicatesPendingToolStep`. Esc-to-cancel lives ONLY on the
 * turn-level status row so the affordance is unique.
 */
export const ProgressBar: React.FC<ProgressBarProps> = React.memo(({ event }) => {
  const { theme } = useTheme();
  const tick = useAnimationTick();

  const steps = event.steps;
  const activeIdx = steps.findIndex((s) => s.status === 'active');
  const lastIdx = steps.length - 1;
  const current = steps[activeIdx >= 0 ? activeIdx : lastIdx];
  const doneCount = steps.filter((s) => s.status === 'done').length;

  let icon = '·';
  let iconColor = theme.colors.text.dim;
  if (current?.status === 'active') {
    icon = SPINNER_FRAMES[tick % SPINNER_FRAMES.length];
    iconColor = theme.colors.text.ethereal;
  } else if (current?.status === 'error') {
    icon = '✗';
    iconColor = theme.colors.status.error;
  } else if (steps.length > 0 && doneCount === steps.length) {
    icon = '✓';
    iconColor = theme.colors.status.success;
  }

  return (
    <Box flexDirection="row" width="100%" marginBottom={1} paddingX={1} alignItems="center">
      <Box width={2} flexShrink={0}>
        <Text color={iconColor}>{icon}</Text>
      </Box>
      <Text color={theme.colors.text.bright} wrap="truncate-end">
        {current?.label ?? event.label}
      </Text>
      {steps.length > 1 && (
        <Text color={theme.colors.text.muted}>
          {' '}
          {doneCount}/{steps.length}
        </Text>
      )}
      {typeof event.percent === 'number' && event.percent > 0 && event.percent < 100 && (
        <Text color={theme.colors.text.muted}> · {Math.round(event.percent)}%</Text>
      )}
    </Box>
  );
});

ProgressBar.displayName = 'ProgressBar';
