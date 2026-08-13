import { Box, Text } from 'ink';
import React from 'react';
import { useTheme } from '../../../theme/ThemeContext';
import type { MessageEvent } from '../../../types/scenario';
import { TerminalMarkdown } from './TerminalMarkdown';

interface MessageBlockProps {
  event: MessageEvent;
}

export const MessageBlock: React.FC<MessageBlockProps> = React.memo(({ event }) => {
  const { theme } = useTheme();

  const hasContent = event.text && event.text.trim().length > 0;

  return (
    <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
      {hasContent && (
        <Box paddingLeft={1} flexDirection="column">
          <TerminalMarkdown content={event.text} />
        </Box>
      )}
      {!hasContent && !event.partial && (
        <Box paddingLeft={1} flexDirection="column">
          <Text color={theme.colors.text.muted} italic>
            (empty response)
          </Text>
        </Box>
      )}
    </Box>
  );
});
