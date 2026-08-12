import { Box, Text } from 'ink';
import React from 'react';
import { SPINNER_FRAMES } from '../constants/animation';
import { useAnimationTick } from '../context/AnimationContext';
import { useTheme } from '../theme/ThemeContext';
import { formatDuration } from '../utils/text';

/** Rotating boot-stage captions (generic diagnostics, not scenario-specific). */
const BOOT_STAGES = [
  'Warming up interface',
  'Loading tool schemas',
  'Connecting to providers',
  'Preparing workspace',
] as const;

/** Animated waveform characters used for the sweeping shuttle line. */
const WAVE_FRAMES = ['▁', '▂', '▃', '▄', '▅', '▆', '▇', '█', '▇', '▆', '▅', '▄', '▃', '▂'] as const;
const DOTS = ['   ', '•  ', '•• ', '•••'] as const;
/** Animated shuttling head width (columns of the sweep). */
const SHUTTLE_HEAD_WIDTH = 3;

export const BootLoading: React.FC = React.memo(() => {
  const { theme } = useTheme();
  const tick = useAnimationTick();

  // Flowing gradient wordmark built from the theme's logo palette (no literals).
  const wordmark = 'ZENITH'.split('').map((ch, index) => (
    <Text key={index} color={theme.colors.logo[(tick + index * 2) % theme.colors.logo.length]} bold>
      {ch}
    </Text>
  ));

  const stage = BOOT_STAGES[Math.floor(tick / 30) % BOOT_STAGES.length];
  const dots = DOTS[Math.floor(tick / 2) % DOTS.length];

  const columns = Math.max(24, process.stdout.columns ?? 80);
  const width = Math.min(40, columns - 6);
  const head = tick % width;
  const shimmer = Array.from({ length: width }).map((_, index) => {
    const distance = Math.abs(index - head);
    const intensity = Math.max(0, 1 - distance / (width / 2));
    const frameIndex = Math.max(0, Math.min(WAVE_FRAMES.length - 1, Math.floor(intensity * (WAVE_FRAMES.length - 1))));
    const color = theme.colors.logo[(index + Math.floor(tick / 8)) % theme.colors.logo.length];
    return (
      <Text key={index} color={color}>
        {distance <= SHUTTLE_HEAD_WIDTH ? '▓' : WAVE_FRAMES[frameIndex]}
      </Text>
    );
  });

  const elapsed = formatDuration(tick * 100);

  return (
    <Box flexDirection="column" width="100%" minHeight={7} alignItems="center" justifyContent="center">
      <Box flexDirection="row" alignItems="center">
        <Text color={theme.colors.status.info} bold>
          {SPINNER_FRAMES[tick % SPINNER_FRAMES.length]}{' '}
        </Text>
        {wordmark}
      </Box>

      <Box flexDirection="row" alignItems="center">
        <Text color={theme.colors.text.bright} bold>
          {stage}
          {dots}
        </Text>
        <Text color={theme.colors.text.dim}> · </Text>
        <Text color={theme.colors.text.muted}>{elapsed}</Text>
      </Box>

      <Box flexDirection="row" marginTop={1}>
        {shimmer}
      </Box>
    </Box>
  );
});

BootLoading.displayName = 'BootLoading';
