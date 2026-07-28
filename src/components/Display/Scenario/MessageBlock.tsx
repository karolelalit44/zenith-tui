import { Box, Text } from 'ink';
import React, { useEffect, useState } from 'react';
import { ASCII_SPINNER_FRAMES } from '../../../constants/animation';
import { useTheme } from '../../../theme/ThemeContext';
import type { MessageEvent } from '../../../types/scenario';
import { TerminalMarkdown } from './TerminalMarkdown';

interface MessageBlockProps {
  event: MessageEvent;
}

export const MessageBlock: React.FC<MessageBlockProps> = React.memo(({ event }) => {
  const { theme } = useTheme();
  const [frameIdx, setFrameIdx] = useState(0);

  useEffect(() => {
    if (!event.partial) return;
    const id = setInterval(() => setFrameIdx((v) => (v + 1) % ASCII_SPINNER_FRAMES.length), 100);
    return () => clearInterval(id);
  }, [event.partial]);

  const hasContent = event.text && event.text.trim().length > 0;

  const icon = event.partial ? (
    <Text color={theme.colors.status.accent}> {ASCII_SPINNER_FRAMES[frameIdx % ASCII_SPINNER_FRAMES.length]}</Text>
  ) : null;

  return (
    <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
      <Box flexDirection="row" alignItems="center" marginBottom={hasContent ? 1 : 0}>
        <Text color={theme.colors.status.accent} bold>
          ◇
        </Text>
        <Text color={theme.colors.text.muted}> Assistant</Text>
        {icon}
      </Box>
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
