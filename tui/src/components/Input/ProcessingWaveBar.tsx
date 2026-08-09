import { Box, Text } from 'ink';
import React from 'react';
import { useAnimationTick } from '../../context/AnimationContext';
import { useTheme } from '../../theme/ThemeContext';
import { formatDuration } from '../../utils/text';

interface ProcessingWaveBarProps {
  isRunning: boolean;
  actionLabel?: string | null;
  startTime?: number;
}

const WAVE_CHARS = ['░', '▒', '▓', '█', '▓', '▒', '░', ' '];
const WAVE_COLORS = ['#00F2FE', '#38EF7D', '#11998E', '#50C878', '#5DADE2', '#7CA87C'];

export const ProcessingWaveBar: React.FC<ProcessingWaveBarProps> = React.memo(
  ({ isRunning, actionLabel, startTime }) => {
    const { theme } = useTheme();
    const tick = useAnimationTick();

    if (!isRunning) {
      return null;
    }

    const elapsedMs = startTime ? Math.max(0, Date.now() - startTime) : tick * 100;
    const elapsedStr = formatDuration(elapsedMs);

    const waveWidth = 10;
    const waveElements = Array.from({ length: waveWidth }).map((_, i) => {
      const charIdx = (tick + i) % WAVE_CHARS.length;
      const colorIdx = (tick + i) % WAVE_COLORS.length;
      return (
        <Text key={i} color={WAVE_COLORS[colorIdx]} bold>
          {WAVE_CHARS[charIdx]}
        </Text>
      );
    });

    const displayLabel = actionLabel || 'Processing request...';

    return (
      <Box flexDirection="row" alignItems="center" width="100%" marginBottom={0} paddingX={1}>
        <Box flexDirection="row" marginRight={1}>
          {waveElements}
        </Box>
        <Text color={theme.colors.text.bright} bold>
          {displayLabel}
        </Text>
        <Text color={theme.colors.text.dim}> · </Text>
        <Text color={theme.colors.text.muted}>{elapsedStr}</Text>
        <Box flexGrow={1} />
        <Text color={theme.colors.status.warning}>Esc to cancel</Text>
      </Box>
    );
  },
);

ProcessingWaveBar.displayName = 'ProcessingWaveBar';
