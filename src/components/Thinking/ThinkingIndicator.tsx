import React, { useState, useEffect } from 'react';
import { Box, Text } from 'ink';
import { useTheme } from '../../theme/ThemeContext';
import { ThinkingIndicatorProps, ThinkingTimerProps } from './types';
import { PHASE_META, INTERRUPT_HINT } from './data/thinkingData';

const THINKING_FRAMES = ['◈', '◇', '◈', '◆'];
const PULSE_FRAMES = ['⣾', '⣽', '⣻', '⢿', '⡿', '⣟', '⣯', '⣷'];

const ThinkingTimer: React.FC<ThinkingTimerProps> = ({ isActive }) => {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (!isActive) {
      setElapsed(0);
      return;
    }
    const start = Date.now();
    const interval = setInterval(() => {
      setElapsed(Date.now() - start);
    }, 100);
    return () => clearInterval(interval);
  }, [isActive]);

  if (!isActive) return null;

  const seconds = (elapsed / 1000).toFixed(1);
  return (
    <Text color="muted" dimColor>
      {' '}{seconds}s
    </Text>
  );
};

export const ThinkingIndicator: React.FC<ThinkingIndicatorProps> = ({
  phase,
  message,
  steps,
  currentStepIndex = 0,
  showElapsed = true,
  compact = false,
}) => {
  const { theme } = useTheme();
  const [tick, setTick] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => setTick(t => t + 1), 80);
    return () => clearInterval(interval);
  }, []);

  const phaseMeta = PHASE_META[phase] || PHASE_META.thinking;
  const spinnerChar = phase === 'thinking' || phase === 'analyzing'
    ? THINKING_FRAMES[tick % THINKING_FRAMES.length]
    : PULSE_FRAMES[tick % PULSE_FRAMES.length];

  const color = theme.colors.text[phaseMeta.colorKey] || theme.colors.text.emerald;

  if (compact) {
    return (
      <Box flexDirection="row" marginBottom={1}>
        <Box width={2}>
          <Text color={color}>{spinnerChar}</Text>
        </Box>
        <Text color={theme.colors.text.ethereal} bold>{phaseMeta.label}</Text>
        <Text color={theme.colors.text.muted}> {message}</Text>
        {showElapsed && <ThinkingTimer isActive={true} />}
      </Box>
    );
  }

  return (
    <Box flexDirection="column" marginBottom={1} paddingX={1}>
      {/* Main indicator row */}
      <Box flexDirection="row" alignItems="center">
        <Box width={2}>
          <Text color={color}>{spinnerChar}</Text>
        </Box>
        <Text color={color} bold>{phaseMeta.label}</Text>
        <Text color={theme.colors.text.muted}> · </Text>
        <Text color={theme.colors.text.ethereal}>{message}</Text>
        {showElapsed && <ThinkingTimer isActive={true} />}
      </Box>

      {/* Step progress bar */}
      {steps && steps.length > 0 && (
        <Box flexDirection="column" marginTop={1} paddingLeft={2}>
          {steps.map((step, idx) => {
            const isComplete = idx < currentStepIndex;
            const isCurrent = idx === currentStepIndex;
            const isPending = idx > currentStepIndex;

            let stepIcon = '○';
            let stepColor = theme.colors.text.muted;
            if (isComplete) {
              stepIcon = '●';
              stepColor = theme.colors.text.emerald;
            } else if (isCurrent) {
              stepIcon = PULSE_FRAMES[tick % PULSE_FRAMES.length];
              stepColor = theme.colors.text.warning;
            }

            return (
              <Box key={idx} flexDirection="row" alignItems="center">
                <Box width={2}>
                  <Text color={stepColor}>{stepIcon}</Text>
                </Box>
                <Text
                  color={isCurrent ? theme.colors.text.ethereal : theme.colors.text.muted}
                  bold={isCurrent}
                  dimColor={isPending}
                >
                  {step.label}
                </Text>
                {isComplete && (
                  <Text color={theme.colors.text.emerald}> ✓</Text>
                )}
              </Box>
            );
          })}
        </Box>
      )}

      {/* Interrupt hint */}
      <Box marginTop={0} paddingLeft={2}>
        <Text color={theme.colors.text.muted} dimColor>
          {INTERRUPT_HINT}
        </Text>
      </Box>
    </Box>
  );
};
