import { Box, Text } from 'ink';
import React, { useEffect, useState } from 'react';
import { formatKeyBind } from '../../../config/keybind';
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
  const toggleHint = formatKeyBind('thinking');

  const isCollapsed = context?.thinkingCollapsed ?? true;
  const historical = context?.isHistorical ?? false;
  const [visibleCount, setVisibleCount] = useState(historical ? event.thoughts.length : 0);

  useEffect(() => {
    setVisibleCount(event.thoughts.length);
  }, [event.thoughts.length]);

  if (!hasRealReasoning(event)) {
    return null;
  }

  const displayedThoughts = isCollapsed || historical ? event.thoughts : event.thoughts.slice(0, visibleCount);

  const durationStr = event.duration > 0 ? formatDuration(event.duration) : '';
  const firstRealThought = event.thoughts
    .map((thought) => getThoughtText(thought).trim())
    .find((text) => text.length > 0 && !STATUS_THOUGHT_RE.test(text));
  const preview =
    firstRealThought && firstRealThought.length > 72 ? `${firstRealThought.slice(0, 71)}…` : firstRealThought;

  return (
    <Box flexDirection="column" width="100%" marginBottom={isCollapsed ? 0 : 1} paddingX={1}>
      {isCollapsed ? (
        <Box flexDirection="row" alignItems="center" width="100%" flexWrap="nowrap">
          <Text color={theme.colors.status.info} bold>
            ▶ Thinking:{' '}
          </Text>
          {durationStr ? <Text color={theme.colors.text.muted}>Thought for {durationStr} </Text> : null}
          {preview ? (
            <Box flexShrink={1}>
              <Text color={theme.colors.text.dim} italic wrap="truncate-end">
                {preview}
              </Text>
            </Box>
          ) : null}
        </Box>
      ) : (
        <Box flexDirection="row" alignItems="center" marginBottom={1}>
          <Text color={theme.colors.status.warning} bold>
            {durationStr ? `Thought: ${durationStr}` : `Thought (${event.thoughts.length} steps)`}
          </Text>
          <Text color={theme.colors.text.dim}> ({toggleHint} to collapse)</Text>
        </Box>
      )}

      {!isCollapsed && (
        <Box flexDirection="column" paddingLeft={2} width="100%">
          {displayedThoughts.map((thought, idx) => {
            const isLatest = !historical && idx === visibleCount - 1 && visibleCount < event.thoughts.length;
            return (
              <Box key={idx} flexDirection="row" alignItems="flex-start" width="100%" marginBottom={0}>
                <Box width={2} flexShrink={0}>
                  <Text color={isLatest ? theme.colors.status.accent : theme.colors.text.muted}>
                    {isLatest ? '>' : '*'}
                  </Text>
                </Box>
                <Box flexShrink={1}>
                  <Text color={isLatest ? theme.colors.text.bright : theme.colors.text.muted} wrap="wrap">
                    {getThoughtText(thought)}
                  </Text>
                </Box>
              </Box>
            );
          })}
        </Box>
      )}
    </Box>
  );
});
