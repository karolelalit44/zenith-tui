import { Box, Text } from 'ink';
import React from 'react';
import { useTheme } from '../../../theme/ThemeContext';
import type { ThinkingEvent, ThinkingThought } from '../../../types/scenario';
import { formatDuration } from '../../../utils/text';

import type { EventRenderContext } from './componentRegistry';

interface ThinkingBlockProps {
  event: ThinkingEvent;
  context?: EventRenderContext;
}

const getThoughtText = (thought: string | ThinkingThought): string =>
  typeof thought === 'string' ? thought : thought.text;

const STATUS_THOUGHT_RE = /^Processing your request\b/i;

function hasRealReasoning(event: ThinkingEvent): boolean {
  return event.thoughts.some((thought) => {
    const text = getThoughtText(thought);
    return Boolean(text) && text.trim().length > 0 && !STATUS_THOUGHT_RE.test(text.trim());
  });
}

export const ThinkingBlock: React.FC<ThinkingBlockProps> = React.memo(({ event, context }) => {
  const { theme } = useTheme();

  // Reasoning is FULLY VISIBLE by default. It only collapses when calm mode
  // is on, or when the user explicitly toggled it (ctrl+h / /think).
  const isCollapsed = context?.calmMode === true || context?.thinkingCollapsed === true;

  if (!hasRealReasoning(event)) {
    return null;
  }

  const isStreaming = event.partial === true && context?.isRunning !== false;
  const durationStr = event.duration > 0 ? formatDuration(event.duration) : '';
  const firstRealThought = event.thoughts
    .map((thought) => getThoughtText(thought).trim())
    .find((text) => text.length > 0 && !STATUS_THOUGHT_RE.test(text));
  const preview =
    firstRealThought && firstRealThought.length >= 72 ? `${firstRealThought.slice(0, 71)}…` : firstRealThought;

  return (
    <Box flexDirection="column" width="100%" marginBottom={isCollapsed ? 0 : 1} paddingX={1}>
      {isCollapsed ? (
        <Box flexDirection="row" alignItems="center" width="100%" flexWrap="nowrap">
          <Text color={theme.colors.status.info}>✻ </Text>
          {durationStr ? (
            <Text color={theme.colors.text.muted}>Thought for {durationStr}</Text>
          ) : (
            <Text color={theme.colors.text.muted}>Thought</Text>
          )}
          {preview ? (
            <>
              <Text color={theme.colors.text.dim}> · </Text>
              <Box flexShrink={1}>
                <Text color={theme.colors.text.dim} italic wrap="truncate-end">
                  {preview}
                </Text>
              </Box>
            </>
          ) : null}
        </Box>
      ) : (
        <Box flexDirection="row" alignItems="center" marginBottom={1}>
          <Text color={theme.colors.status.info} bold>
            ✻ Thinking
          </Text>
          {isStreaming && !durationStr ? (
            <Text color={theme.colors.text.dim}> …</Text>
          ) : durationStr ? (
            <Text color={theme.colors.text.muted}> · {durationStr}</Text>
          ) : null}
        </Box>
      )}

      {!isCollapsed && (
        <Box flexDirection="column" paddingLeft={2} width="100%">
          {event.thoughts.map((thought, idx) => (
            <Box key={idx} flexDirection="row" alignItems="flex-start" width="100%" marginBottom={0}>
              <Box width={2} flexShrink={0}>
                <Text color={theme.colors.text.dim}>│</Text>
              </Box>
              <Box flexShrink={1}>
                <Text color={theme.colors.text.muted} wrap="wrap">
                  {getThoughtText(thought)}
                </Text>
              </Box>
            </Box>
          ))}
        </Box>
      )}
    </Box>
  );
});

ThinkingBlock.displayName = 'ThinkingBlock';
