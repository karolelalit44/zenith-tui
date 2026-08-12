import { Text } from 'ink';
import React from 'react';
import { useTheme } from '../../theme/ThemeContext';

const TOTAL_BLOCKS = 10;

interface ComposerGaugeProps {
  usedTokens: number;
  maxTokens: number;
}

export const ComposerGauge: React.FC<ComposerGaugeProps> = React.memo(({ usedTokens, maxTokens }) => {
  const { theme } = useTheme();
  const percent = maxTokens > 0 ? Math.min(100, Math.round((usedTokens / maxTokens) * 100)) : 0;
  const filledBlocks = Math.max(0, Math.min(TOTAL_BLOCKS, Math.round((percent / 100) * TOTAL_BLOCKS)));
  const gauge = '█'.repeat(filledBlocks) + '░'.repeat(TOTAL_BLOCKS - filledBlocks);
  const color = percent > 80 ? theme.colors.status.warning : theme.colors.status.success;

  return (
    <Text color={color}>
      [{gauge}] {percent}%
    </Text>
  );
});

ComposerGauge.displayName = 'ComposerGauge';
