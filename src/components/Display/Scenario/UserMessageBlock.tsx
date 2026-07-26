import { Box, Text } from 'ink';
import React from 'react';
import { useTheme } from '../../../theme/ThemeContext';

interface UserMessageBlockProps {
  prompt: string;
}

export const UserMessageBlock: React.FC<UserMessageBlockProps> = React.memo(({ prompt }) => {
  const { theme } = useTheme();
  const timeStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });

  return (
    <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
      <Box
        flexDirection="row"
        width="100%"
        paddingX={1}
        paddingY={0}
        borderStyle="round"
        borderColor={theme.colors.border.muted}
      >
        <Text color={theme.colors.text.bright} wrap="wrap">
          {prompt}
        </Text>
      </Box>
      <Box flexDirection="row" justifyContent="flex-end" marginTop={0}>
        <Text color={theme.colors.text.dim}>{timeStr}</Text>
      </Box>
    </Box>
  );
});
