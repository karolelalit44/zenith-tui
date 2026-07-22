import { Box, Text } from 'ink';
import React, { useEffect, useState } from 'react';
import { useTheme } from '../../../theme/ThemeContext';
import type { ThinkingEvent, ThinkingThought } from '../../../types/scenario';

import type { EventRenderContext } from './componentRegistry';

interface ThinkingBlockProps {
  event: ThinkingEvent;
  collapsed?: boolean;
  isHistorical?: boolean;
  context?: EventRenderContext;
}

const getThoughtText = (thought: string | ThinkingThought): string =>
  typeof thought === 'string' ? thought : thought.text;

const getThoughtDelay = (thought: string | ThinkingThought, index: number): number =>
  typeof thought === 'string' ? 0 : (thought.delay ?? index * 400);

export const ThinkingBlock: React.FC<ThinkingBlockProps> = React.memo(({ event, collapsed, isHistorical, context }) => {
  const { theme } = useTheme();
  const isCollapsed = context?.thinkingCollapsed ?? collapsed ?? false;
  const historical = context?.isHistorical ?? isHistorical ?? false;
  const [visibleCount, setVisibleCount] = useState(historical ? event.thoughts.length : 0);

  useEffect(() => {
    if (isCollapsed || historical) {
      setVisibleCount(event.thoughts.length);
      return;
    }

    const thoughts = event.thoughts;
    let cancelled = false;
    let cumulativeDelay = 0;

    thoughts.forEach((thought, idx) => {
      cumulativeDelay += Math.min(150, getThoughtDelay(thought, idx));

      const revealTimer = setTimeout(() => {
        if (!cancelled) setVisibleCount(idx + 1);
      }, cumulativeDelay);

      void revealTimer;
    });

    return () => {
      cancelled = true;
    };
  }, [event.thoughts, isCollapsed, historical]);

  const displayedThoughts = isCollapsed || historical ? event.thoughts : event.thoughts.slice(0, visibleCount);

  return (
    <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
      <Box flexDirection="row" alignItems="center" marginBottom={isCollapsed ? 0 : 1} flexWrap="wrap">
        <Text color={theme.colors.status.accent} bold>
          {isCollapsed ? '▸' : '▾'} Thinking
        </Text>
        <Text color={theme.colors.text.muted}> ({event.thoughts.length} steps)</Text>
        <Text color={theme.colors.text.muted}> · </Text>
        <Text color={theme.colors.text.muted} bold underline>
          Shift+T to toggle
        </Text>
      </Box>

      {!isCollapsed && (
        <Box flexDirection="column" paddingLeft={2} width="100%">
          {displayedThoughts.map((thought, idx) => {
            const isLatest = !isHistorical && idx === visibleCount - 1 && visibleCount < event.thoughts.length;
            return (
              <Box key={idx} flexDirection="row" alignItems="center" width="100%">
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
