import React from 'react';
import { Box, Text } from 'ink';
import { useTheme } from '../../../theme/ThemeContext';

interface DividerProps {
  height?: number;
}

export const Divider: React.FC<DividerProps> = ({ height = 11 }) => {
  const { theme } = useTheme();
  const lines = Array(height).fill('║').join('\n');
  return (
    <Box width={1} justifyContent="center" alignItems="center">
      <Text color={theme.colors.border.muted}>{lines}</Text>
    </Box>
  );
};
