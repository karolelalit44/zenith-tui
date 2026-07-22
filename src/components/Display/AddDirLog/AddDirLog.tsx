import React from 'react';
import { Box, Text } from 'ink';
import { useTheme } from '../../../theme/ThemeContext';
import { AddDirLogProps } from './types';
import { ADD_DIR_DATA } from '../data/addDirData';

export const AddDirLog: React.FC<AddDirLogProps> = ({ path }) => {
  const { theme } = useTheme();

  return (
    <Box flexDirection="column" marginBottom={1} paddingX={1} borderStyle="round" borderColor={theme.colors.border.muted}>
      <Box flexDirection="row" borderStyle="single" borderTop={false} borderLeft={false} borderRight={false} borderColor={theme.colors.border.muted} paddingBottom={1} marginBottom={1}>
        <Text color={theme.colors.text.emerald}>⌕ </Text>
        <Text color={theme.colors.text.ethereal} bold>{ADD_DIR_DATA.headerLabel}</Text>
        <Text color={theme.colors.text.muted}> │ </Text>
        <Text color={theme.colors.text.muted}>{path}</Text>
      </Box>

      <Box flexDirection="row" marginBottom={1} justifyContent="space-around">
        {ADD_DIR_DATA.metrics.map((metric, idx) => (
          <Box key={idx} flexDirection="column" alignItems="center">
            <Text color={theme.colors.text.muted}>{metric.label}</Text>
            <Text color={metric.isWarning ? theme.colors.text.warning : theme.colors.text.ethereal} bold>{metric.value}</Text>
          </Box>
        ))}
      </Box>

      <Box flexDirection="row" paddingLeft={1}>
        <Text color={theme.colors.text.emerald}>✔ </Text>
        <Text color={theme.colors.text.muted}>{ADD_DIR_DATA.statusMessage}</Text>
      </Box>
    </Box>
  );
};
