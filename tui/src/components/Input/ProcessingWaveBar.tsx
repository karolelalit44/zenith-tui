import { Box, Text } from 'ink';
import React from 'react';
import { SPINNER_FRAMES } from '../../constants/animation';
import { useAnimationTick } from '../../context/AnimationContext';
import { formatTokenCount } from '../../services/api/tokenEstimationService';
import { useTheme } from '../../theme/ThemeContext';
import { formatDuration } from '../../utils/text';

interface ProcessingWaveBarProps {
  isRunning: boolean;
  actionLabel?: string | null;
  startTime?: number;
  tokenCount?: number;
}

/** Animated waveform characters for the equalizer bars. */
const WAVE_FRAMES = ['▁', '▂', '▃', '▄', '▅', '▆', '▇', '█', '▇', '▆', '▅', '▄', '▃', '▂'] as const;
const DOTS = ['   ', '•  ', '•• ', '•••'] as const;
const EQUALIZER_BARS = 8;

export const ProcessingWaveBar: React.FC<ProcessingWaveBarProps> = React.memo(
  ({ isRunning, actionLabel, startTime, tokenCount }) => {
    const { theme } = useTheme();
    const tick = useAnimationTick();

    if (!isRunning) {
      return null;
    }

    const elapsedMs = startTime ? Math.max(0, Date.now() - startTime) : tick * 100;
    const elapsedStr = formatDuration(elapsedMs);

    // Theme-derived gradient used for animation accents.
    const gradient = [
      theme.colors.status.accent,
      theme.colors.text.emerald,
      theme.colors.status.success,
      theme.colors.status.info,
      theme.colors.status.accent,
    ];

    // Filter out redundant default "Thinking" labels since thinking has its own dedicated section
    const labelText =
      actionLabel?.trim() && actionLabel.trim().toLowerCase() !== 'thinking' ? actionLabel.trim() : null;
    const labelEl = labelText
      ? labelText.split('').map((ch, index) => (
          <Text key={index} color={gradient[(tick + index * 2) % gradient.length]} bold>
            {ch}
          </Text>
        ))
      : null;

    // Animated sine equalizer bars tinted by theme gradient.
    const bars = Array.from({ length: EQUALIZER_BARS }).map((_, index) => {
      const phase = (Math.sin(tick / 3 + index * 0.85) + 1) / 2;
      const frameIndex = Math.max(0, Math.min(WAVE_FRAMES.length - 1, Math.floor(phase * (WAVE_FRAMES.length - 1))));
      const color = gradient[(index + Math.floor(tick / 3)) % gradient.length];
      return (
        <Box key={index} width={1}>
          <Text color={color}>{WAVE_FRAMES[frameIndex]}</Text>
        </Box>
      );
    });

    const dots = DOTS[Math.floor(tick / 2) % DOTS.length];

    return (
      <Box flexDirection="row" alignItems="center" width="100%" paddingX={1} flexWrap="nowrap" overflow="hidden">
        {/* Spinner */}
        <Box flexDirection="row" marginRight={1} flexShrink={0}>
          <Text color={theme.colors.status.info} bold wrap="truncate-end">
            {SPINNER_FRAMES[tick % SPINNER_FRAMES.length]}
          </Text>
        </Box>

        {/* Equalizer bars */}
        <Box flexDirection="row" marginRight={1} alignItems="flex-end" flexShrink={0}>
          {bars}
        </Box>

        {/* Custom action label (if provided and not default "Thinking") */}
        {labelEl && (
          <Box flexDirection="row" flexShrink={1} overflow="hidden" marginRight={1}>
            {labelEl}
            <Text color={theme.colors.text.dim} wrap="truncate-end">{dots}</Text>
          </Box>
        )}

        {/* Elapsed duration (on left) */}
        <Box flexDirection="row" alignItems="center" flexShrink={0}>
          <Text color={theme.colors.text.muted} wrap="truncate-end">{elapsedStr}</Text>
        </Box>

        {/* Live token usage (on left) */}
        {Boolean(tokenCount && tokenCount > 0) && (
          <Box flexDirection="row" alignItems="center" flexShrink={0}>
            <Text color={theme.colors.text.dim} wrap="truncate-end"> · </Text>
            <Text color={theme.colors.text.emerald} wrap="truncate-end">
              {formatTokenCount(tokenCount!)} tokens
            </Text>
          </Box>
        )}

        {/* Flex spacer pushing Esc hint to far right */}
        <Box flexGrow={1} />

        {/* Right side: Esc to cancel only */}
        <Box flexDirection="row" alignItems="center" flexShrink={0} marginLeft={1}>
          <Text color={theme.colors.status.warning} wrap="truncate-end">Esc to cancel</Text>
        </Box>
      </Box>
    );
  },
);

ProcessingWaveBar.displayName = 'ProcessingWaveBar';
