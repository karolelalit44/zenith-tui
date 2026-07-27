import { Box, Text } from 'ink';
import React from 'react';
import { useTheme } from '../../../theme/ThemeContext';

interface UserMessageBlockProps {
  prompt: string;
}

export const UserMessageBlock: React.FC<UserMessageBlockProps> = React.memo(({ prompt }) => {
  const { theme } = useTheme();
  const columns = process.stdout.columns ?? 80;
  const isCompact = columns < 75;

  const now = new Date();
  const timeStr = isCompact
    ? now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false })
    : `${now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false })}, ${now.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })}`;

  return (
    <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
      <Box
        flexDirection="column"
        width="100%"
        paddingX={1}
        paddingY={0}
        borderStyle="round"
        borderColor={theme.colors.border.muted}
      >
        <Box flexDirection="row" width="100%">
          <Text color={theme.colors.text.bright} wrap="wrap">
            {prompt}
          </Text>
        </Box>
        <Box flexDirection="row" justifyContent="flex-end" width="100%">
          <Text color={theme.colors.text.dim} wrap="truncate-end">{timeStr}</Text>
        </Box>
      </Box>
    </Box>
  );
});
