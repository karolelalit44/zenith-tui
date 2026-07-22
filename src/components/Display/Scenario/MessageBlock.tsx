import { Box, Text } from 'ink';
import React from 'react';
import { useTheme } from '../../../theme/ThemeContext';
import type { MessageEvent } from '../../../types/scenario';

interface MessageBlockProps {
  event: MessageEvent;
}

export const MessageBlock: React.FC<MessageBlockProps> = ({ event }) => {
  const { theme } = useTheme();

  return (
    <Box flexDirection="row" marginBottom={1} paddingX={1}>
      <Text color={theme.colors.text.muted}>● </Text>
      <Text color={theme.colors.text.ethereal}>{event.text}</Text>
    </Box>
  );
};
