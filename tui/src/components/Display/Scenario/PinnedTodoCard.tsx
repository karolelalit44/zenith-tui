import { Box, Text } from 'ink';
import React from 'react';
import { useAnimationTick } from '../../../context/AnimationContext';
import { useTerminalDimensions } from '../../../hooks/useTerminalDimensions';
import { useTheme } from '../../../theme/ThemeContext';
import type { TodoItem, TodoStatus } from '../../../types/scenario';
import type { ConsolidatedTodoBoard } from '../../../utils/todoBoard';

const SPINNER_FRAMES = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'];
const MAX_PINNED_TODOS = 5;
const PROGRESS_BAR_WIDTH = 10;

interface PinnedTodoCardProps {
  event: ConsolidatedTodoBoard;
  isRunning?: boolean;
}

export const PinnedTodoCard: React.FC<PinnedTodoCardProps> = React.memo(({ event, isRunning = false }) => {
  const { theme } = useTheme();
  const colors = theme.colors;
  const tick = useAnimationTick();
  const { columns } = useTerminalDimensions();
  const termCols = columns || process.stdout.columns || 80;
  const contentWidth = Math.max(30, termCols - 2);

  const all = event.board ?? [];
  if (all.length === 0) return null;

  const doneCount = all.filter((t) => t.status === 'done').length;
  const totalCount = all.length;
  const percent = totalCount > 0 ? Math.round((doneCount / totalCount) * 100) : 0;

  // Build progress bar: e.g. [██████░░░░]
  const filledWidth = Math.round((percent / 100) * PROGRESS_BAR_WIDTH);
  const emptyWidth = PROGRESS_BAR_WIDTH - filledWidth;
  const progressBarStr = `[${'█'.repeat(filledWidth)}${'░'.repeat(emptyWidth)}]`;

  // Determine active in-progress task for header ticker
  const activeTask = all.find((t) => t.status === 'in_progress');

  // Limit visible items to MAX_PINNED_TODOS
  const items = all.slice(0, MAX_PINNED_TODOS);
  const hiddenCount = all.length - items.length;

  const renderStatusIcon = (status: TodoStatus) => {
    switch (status) {
      case 'done':
        return <Text color={colors.status.success}>✔</Text>;
      case 'in_progress':
        return (
          <Text color={colors.status.info} bold>
            {isRunning ? SPINNER_FRAMES[tick % SPINNER_FRAMES.length] : '◐'}
          </Text>
        );
      case 'blocked':
      case 'cancelled':
        return <Text color={colors.status.error}>✖</Text>;
      default:
        return <Text color={colors.text.dim}>○</Text>;
    }
  };

  const getTitleColor = (status: TodoStatus): string => {
    switch (status) {
      case 'done':
        return colors.text.muted;
      case 'in_progress':
        return colors.text.bright;
      case 'blocked':
      case 'cancelled':
        return colors.status.error;
      default:
        return colors.text.muted;
    }
  };

  return (
    <Box
      flexDirection="column"
      width={contentWidth}
      backgroundColor={colors.code.background}
      borderStyle="round"
      borderColor={isRunning ? colors.border.active : colors.border.muted}
      paddingX={1}
      paddingY={0}
    >
      {/* Header row: Title + Progress Bar + Percent + Active Ticker */}
      <Box flexDirection="row" width="100%" justifyContent="space-between" alignItems="center">
        <Box flexDirection="row" alignItems="center">
          <Text color={colors.text.bright} bold>
            Tasks{' '}
          </Text>
          <Text color={colors.text.dim}>
            ({doneCount}/{totalCount}){' '}
          </Text>
          <Text color={percent === 100 ? colors.status.success : colors.status.info}>{progressBarStr} </Text>
          <Text color={colors.text.muted}>{percent}%</Text>
        </Box>

        {activeTask ? (
          <Box flexDirection="row" alignItems="center" flexShrink={1} marginLeft={1}>
            <Text color={colors.status.info} bold>
              {isRunning ? `${SPINNER_FRAMES[tick % SPINNER_FRAMES.length]} ` : '◐ '}
            </Text>
            <Text color={colors.text.bright} wrap="truncate-end">
              {activeTask.title}
            </Text>
          </Box>
        ) : percent === 100 ? (
          <Text color={colors.status.success} bold>
            ✔ All complete
          </Text>
        ) : null}
      </Box>

      {/* Task items */}
      <Box flexDirection="column" marginTop={0}>
        {items.map((item: TodoItem) => (
          <Box key={item.id} flexDirection="row" width="100%" alignItems="center">
            <Box width={2} flexShrink={0}>
              {renderStatusIcon(item.status)}
            </Box>
            <Box width={4} flexShrink={0}>
              <Text color={colors.text.dim}>{item.id}</Text>
            </Box>
            <Box flexGrow={1} flexShrink={1}>
              <Text
                color={getTitleColor(item.status)}
                strikethrough={item.status === 'done'}
                bold={item.status === 'in_progress'}
                wrap="truncate-end"
              >
                {item.title}
              </Text>
            </Box>
            {item.priority && item.priority !== 'medium' && (
              <Box marginLeft={1} flexShrink={0}>
                <Text color={item.priority === 'high' ? colors.status.accent : colors.text.dim}>
                  [{item.priority}]
                </Text>
              </Box>
            )}
          </Box>
        ))}
      </Box>

      {hiddenCount > 0 && (
        <Box marginTop={0}>
          <Text color={colors.text.dim}>+{hiddenCount} more tasks…</Text>
        </Box>
      )}
    </Box>
  );
});

PinnedTodoCard.displayName = 'PinnedTodoCard';
