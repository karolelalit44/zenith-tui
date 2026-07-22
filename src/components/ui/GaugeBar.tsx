import { Text } from 'ink';
import React from 'react';

interface GaugeBarProps {
  current: number;
  total: number;
  width?: number;
  color?: string;
}

export const GaugeBar: React.FC<GaugeBarProps> = ({ current, total, width = 20, color = 'green' }) => {
  const ratio = total > 0 ? current / total : 0;
  const filled = Math.round(ratio * width);
  const empty = width - filled;
  return (
    <Text color={color}>
      {'█'.repeat(filled)}
      {'░'.repeat(empty)} {current}/{total}
    </Text>
  );
};
