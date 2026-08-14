import { Box, Text } from 'ink';
import React from 'react';
import { SPINNER_FRAMES } from '../../../constants/animation';
import { useAnimationTick } from '../../../context/AnimationContext';
import { useTheme } from '../../../theme/ThemeContext';
import type { TodoStatus } from '../../../types/scenario';
import type { ConsolidatedTodoBoard } from '../../../utils/todoBoard';
import type { EventRenderContext } from './componentRegistry';

interface TodoBoardBlockProps {
  event: ConsolidatedTodoBoard;
  context?: EventRenderContext;
}

function checkboxStyle(status: TodoStatus, colors: Record<string, any>, tick: number): { icon: string; color: string } {
  switch (status) {
    case 'done':
      return { icon: '☑', color: colors.status.success };
    case 'in_progress':
      return { icon: SPINNER_FRAMES[tick % SPINNER_FRAMES.length], color: colors.status.info };
    case 'blocked':
      return { icon: '⊘', color: colors.status.warning };
    case 'cancelled':
      return { icon: '✕', color: colors.text.dim };
    default:
      return { icon: '☐', color: colors.text.dim };
  }
}

export const TodoBoardBlock: React.FC<TodoBoardBlockProps> = React.memo(({ event }) => {
  const { theme } = useTheme();
  const colors = theme.colors;
  const tick = useAnimationTick();

  const isLive = event.activity.length === 0 || event.activity[event.activity.length - 1].action !== 'completed';

  return (
    <Box flexDirection="column" width="100%" marginTop={1} marginBottom={1}>
      <Box
        flexDirection="column"
        backgroundColor={colors.code.background}
        borderStyle="round"
        borderColor={isLive ? colors.border.active : colors.border.muted}
        paddingX={1}
        paddingY={0}
      >
        {/* Header */}
        <Box flexDirection="row" alignItems="center">
          <Text color={colors.text.bright} bold>
            ☑ TODO BOARD
          </Text>
          <Text color={colors.text.dim}> · </Text>
          <Text color={isLive ? colors.status.info : colors.status.success} bold>
            {isLive ? `${SPINNER_FRAMES[tick % SPINNER_FRAMES.length]} LIVE SIMULATION` : '✓ SIMULATION COMPLETE'}
          </Text>
        </Box>

        {/* Task list */}
        <Box flexDirection="column" paddingLeft={1}>
          {event.board.map((item) => {
            const cb = checkboxStyle(item.status, colors, tick);
            return (
              <Box key={item.id} flexDirection="row" alignItems="center">
                <Box width={2}>
                  <Text color={cb.color}>{cb.icon}</Text>
                </Box>
                <Text color={item.status === 'done' ? colors.text.muted : colors.text.bright} wrap="truncate-end">
                  {item.title}
                </Text>
              </Box>
            );
          })}
        </Box>
      </Box>
    </Box>
  );
});

TodoBoardBlock.displayName = 'TodoBoardBlock';
