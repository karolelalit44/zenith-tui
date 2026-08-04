import { Box, Text } from 'ink';
import React, { useEffect, useState } from 'react';
import { useTheme } from '../../../theme/ThemeContext';
import type { ThinkingEvent, ThinkingThought } from '../../../types/scenario';

import type { EventRenderContext } from './componentRegistry';

interface ThinkingBlockProps {
  event: ThinkingEvent;
  context?: EventRenderContext;
}

const getThoughtText = (thought: string | ThinkingThought): string =>
  typeof thought === 'string' ? thought : thought.text;

const _getThoughtDelay = (thought: string | ThinkingThought, index: number): number =>
  typeof thought === 'string' ? 0 : (thought.delay ?? index * 400);

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(1)}s`;
  const m = Math.floor(s / 60);
  const rem = (s % 60).toFixed(0);
  return `${m}m ${rem}s`;
}

export const ThinkingBlock: React.FC<ThinkingBlockProps> = React.memo(({ event, context }) => {
  const { theme } = useTheme();
  const isCollapsed = context?.thinkingCollapsed ?? true;
  const historical = context?.isHistorical ?? false;
  const [visibleCount, setVisibleCount] = useState(historical ? event.thoughts.length : 0);

  useEffect(() => {
    setVisibleCount(event.thoughts.length);
  }, [event.thoughts.length]);

  const displayedThoughts = isCollapsed || historical ? event.thoughts : event.thoughts.slice(0, visibleCount);

  const durationStr = event.duration > 0 ? formatDuration(event.duration) : '';
  const headerTitle = durationStr ? `Thought for ${durationStr}` : `Thought (${event.thoughts.length} steps)`;

  return (
    <Box flexDirection="column" width="100%" marginBottom={isCollapsed ? 0 : 1} paddingX={1}>
      <Box flexDirection="row" alignItems="center" marginBottom={isCollapsed ? 0 : 1} flexWrap="wrap">
        <Text color={theme.colors.text.muted}>• </Text>
        <Text color={theme.colors.text.bright}>{headerTitle} </Text>
        <Text color={theme.colors.text.dim}>{isCollapsed ? '(ctrl+o to expand)' : '(ctrl+o to collapse)'}</Text>
      </Box>

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
