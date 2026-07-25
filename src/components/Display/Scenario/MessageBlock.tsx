import { Box, Text } from 'ink';
import React, { useEffect, useState } from 'react';
import { useTheme } from '../../../theme/ThemeContext';
import type { MessageEvent } from '../../../types/scenario';
import { TerminalMarkdown } from './TerminalMarkdown';

interface MessageBlockProps {
  event: MessageEvent;
}

export const MessageBlock: React.FC<MessageBlockProps> = React.memo(({ event }) => {
  const { theme } = useTheme();
  const [showCursor, setShowCursor] = useState(true);

  useEffect(() => {
    if (!event.partial) return;
    const id = setInterval(() => setShowCursor((v) => !v), 500);
    return () => clearInterval(id);
  }, [event.partial]);

  if (!event.text && !event.partial) {
    return null;
  }

  const cursor = event.partial && showCursor ? <Text color={theme.colors.status.accent}> ▌</Text> : null;

  return (
    <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
      <Box flexDirection="row" alignItems="center" marginBottom={0}>
        <Text color={theme.colors.status.accent} bold>
          [ASSISTANT]
        </Text>
        {cursor}
      </Box>
      <Box paddingLeft={1} flexDirection="column">
        <TerminalMarkdown content={event.text} />
      </Box>
    </Box>
  );
});
