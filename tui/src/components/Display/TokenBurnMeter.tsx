import { Text } from 'ink';
import React, { useMemo } from 'react';
import { useTheme } from '../../theme/ThemeContext';

const SPARK_CHARS = ['▁', '▂', '▃', '▄', '▅', '▆', '▇', '█'];

interface TokenBurnMeterProps {
  stepTokens: number[];
  width?: number;
}

const TokenBurnMeter: React.FC<TokenBurnMeterProps> = ({ stepTokens, width = 12 }) => {
  const { theme } = useTheme();

  const sparkline = useMemo(() => {
    if (!stepTokens.length) return '';
    const values = stepTokens.slice(-width);
    const max = Math.max(...values, 1);
    return values.map((v) => SPARK_CHARS[Math.min(7, Math.floor((v / max) * 8))]).join('');
  }, [stepTokens, width]);

  const avg = useMemo(() => {
    if (!stepTokens.length) return 0;
    return Math.round(stepTokens.reduce((a, b) => a + b, 0) / stepTokens.length);
  }, [stepTokens]);

  if (!stepTokens.length) return null;

  const lastColor =
    stepTokens.length > 1 && stepTokens[stepTokens.length - 1] > stepTokens[stepTokens.length - 2] * 1.2
      ? theme.colors.status.warning
      : theme.colors.text.muted;

  return (
    <Text color={lastColor}>
      {sparkline} {avg} avg
    </Text>
  );
};

export { TokenBurnMeter };
