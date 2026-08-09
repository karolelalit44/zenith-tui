import { Box, Text } from 'ink';
import React from 'react';
import { ASCII_SPINNER_FRAMES } from '../../../constants/animation';
import { useAnimationTick } from '../../../context/AnimationContext';
import { modelStore } from '../../../services/providers/ModelStore';
import { useTheme } from '../../../theme/ThemeContext';
import type { MessageEvent } from '../../../types/scenario';
import { TerminalMarkdown } from './TerminalMarkdown';

interface MessageBlockProps {
  event: MessageEvent;
}

export const MessageBlock: React.FC<MessageBlockProps> = React.memo(({ event }) => {
  const { theme } = useTheme();
  const tick = useAnimationTick();

  const hasContent = event.text && event.text.trim().length > 0;
  const modelLabel = modelStore.current ? modelStore.toDisplayString(modelStore.current) : '';

  const icon = event.partial ? (
    <Text color={theme.colors.status.accent}> {ASCII_SPINNER_FRAMES[tick % ASCII_SPINNER_FRAMES.length]}</Text>
  ) : null;

  return (
    <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
      <Box flexDirection="row" alignItems="center" marginBottom={hasContent ? 1 : 0}>
        <Text color={theme.colors.status.accent} bold>
          ◇
        </Text>
        <Text color={theme.colors.text.muted}> Assistant</Text>
        {modelLabel && <Text color={theme.colors.text.dim}> ({modelLabel})</Text>}
        {typeof event.iteration === 'number' && event.iteration > 0 && (
          <Text color={theme.colors.text.dim}> · turn {event.iteration}</Text>
        )}
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
