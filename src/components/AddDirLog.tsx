import React from 'react';
import { Box, Text } from 'ink';
import { useTheme } from '../theme/ThemeContext';

interface AddDirLogProps {
  path: string;
}

export const AddDirLog: React.FC<AddDirLogProps> = ({ path }) => {
  const { theme } = useTheme();
  return (
    <Box flexDirection="column" marginBottom={1} paddingX={1} borderStyle="round" borderColor={theme.colors.border.muted}>
      
      {/* Header */}
      <Box flexDirection="row" borderStyle="single" borderTop={false} borderLeft={false} borderRight={false} borderColor={theme.colors.border.muted} paddingBottom={1} marginBottom={1}>
         <Text color={theme.colors.text.emerald}>⌕ </Text>
         <Text color={theme.colors.text.ethereal} bold>WORKSPACE SYNC</Text>
         <Text color={theme.colors.text.muted}> │ </Text>
         <Text color={theme.colors.text.muted}>{path}</Text>
      </Box>

      {/* Metrics Row */}
      <Box flexDirection="row" marginBottom={1} justifyContent="space-around">
        <Box flexDirection="column" alignItems="center">
          <Text color={theme.colors.text.muted}>Files Indexed</Text>
          <Text color={theme.colors.text.ethereal} bold>1,204</Text>
        </Box>
        <Box flexDirection="column" alignItems="center">
          <Text color={theme.colors.text.muted}>Dependencies</Text>
          <Text color={theme.colors.text.ethereal} bold>32</Text>
        </Box>
        <Box flexDirection="column" alignItems="center">
          <Text color={theme.colors.text.muted}>Context Delta</Text>
          <Text color={theme.colors.text.warning} bold>+14.2 MB</Text>
        </Box>
        <Box flexDirection="column" alignItems="center">
          <Text color={theme.colors.text.muted}>Sync Time</Text>
          <Text color={theme.colors.text.ethereal} bold>842ms</Text>
        </Box>
      </Box>

      {/* Status Footer */}
      <Box flexDirection="row" paddingLeft={1}>
        <Text color={theme.colors.text.emerald}>✔ </Text>
        <Text color={theme.colors.text.muted}>Directory mapped and vectorized. Zenith engine is now tracking this path.</Text>
      </Box>

    </Box>
  );
};
