import React from 'react';
import { Box, Text } from 'ink';
import { useTheme } from '../../../theme/ThemeContext';
import { TreeLogProps } from './types';

export const TreeLog: React.FC<TreeLogProps> = ({ toolName, args, resultTitle, children }) => {
  const { theme } = useTheme();

  return (
    <Box flexDirection="column" marginBottom={1}>
      <Box>
        <Text color={theme.colors.text.emerald}>● </Text>
        <Text color={theme.colors.text.ethereal} bold>{toolName}</Text>
        {args && <Text color={theme.colors.text.muted}>({args})</Text>}
      </Box>

      {(resultTitle || children) && (
        <Box flexDirection="row">
          <Text color={theme.colors.text.muted}>└ </Text>
          <Box flexDirection="column" paddingLeft={1}>
            {resultTitle && <Text color={theme.colors.text.muted}>{resultTitle}</Text>}
            {children && <Box marginTop={1}>{children}</Box>}
          </Box>
        </Box>
      )}
    </Box>
  );
};
