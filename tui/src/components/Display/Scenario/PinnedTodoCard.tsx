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

const LiveSpinner: React.FC = () => {
  const tick = useAnimationTick();
  return <>{SPINNER_FRAMES[tick % SPINNER_FRAMES.length]}</>;
};

export interface ActiveActivityInfo {
  label: string;
  percent?: number;
  tool?: string;
  isThinking?: boolean;
}

interface PinnedTodoCardProps {
  event: ConsolidatedTodoBoard;
  isRunning?: boolean;
  activeActivity?: ActiveActivityInfo;
}

export const PinnedTodoCard: React.FC<PinnedTodoCardProps> = React.memo(
  ({ event, isRunning = false, activeActivity }) => {
    const { theme } = useTheme();
    const colors = theme.colors;
    const { columns } = useTerminalDimensions();
    const termCols = columns || process.stdout.columns || 80;
    const contentWidth = Math.max(30, termCols - 2);

    const all = event.board ?? [];
    if (all.length === 0) return null;

    const doneCount = all.filter((t) => t.status === 'done').length;
    const inProgressCount = all.filter((t) => t.status === 'in_progress').length;
    const blockedCount = all.filter((t) => t.status === 'blocked' || t.status === 'cancelled').length;
    const todoCount = all.filter((t) => t.status === 'todo').length;
    const totalCount = all.length;
    const percent = totalCount > 0 ? Math.round((doneCount / totalCount) * 100) : 0;

    // Build progress bar: e.g. [██████░░░░]
    const clampedPercent = Math.max(0, Math.min(100, percent));
    const rawFilled = Math.round((clampedPercent / 100) * PROGRESS_BAR_WIDTH);
    const filledWidth = Math.max(0, Math.min(PROGRESS_BAR_WIDTH, rawFilled));
    const emptyWidth = PROGRESS_BAR_WIDTH - filledWidth;
    const progressBarStr = `[${'█'.repeat(filledWidth)}${'░'.repeat(emptyWidth)}]`;

    // Determine active in-progress task or next pending task for stage indicator
    const activeTask = all.find((t) => t.status === 'in_progress');
    const nextTask = !activeTask ? all.find((t) => t.status === 'todo') : undefined;

    // Limit visible items to MAX_PINNED_TODOS
    const items = all.slice(0, MAX_PINNED_TODOS);
    const hiddenCount = all.length - items.length;

    const renderStatusBadge = (status: TodoStatus) => {
      switch (status) {
        case 'done':
          return (
            <Text color={colors.status.success} bold>
              ✔ DONE   
            </Text>
          );
        case 'in_progress':
          return (
            <Text color={colors.status.info} bold>
              {isRunning ? <LiveSpinner /> : '◐'} ACTIVE 
            </Text>
          );
        case 'blocked':
          return (
            <Text color={colors.status.error} bold>
              ✖ BLOCKED
            </Text>
          );
        case 'cancelled':
          return (
            <Text color={colors.status.error}>
              ✖ CANCEL 
            </Text>
          );
        default:
          return (
            <Text color={colors.text.dim}>
              ○ PENDING
            </Text>
          );
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
        {/* Header row: Title + Stage Breakdown + Progress Bar + Active Stage Ticker */}
        <Box flexDirection="row" width="100%" justifyContent="space-between" alignItems="center">
          <Box flexDirection="row" alignItems="center">
            <Text color={colors.text.bright} bold>
              Tasks{' '}
            </Text>
            <Text color={colors.text.dim}>
              ({doneCount}/{totalCount}){' '}
            </Text>
            <Text color={colors.status.success} bold>
              ✔ {doneCount}{' '}
            </Text>
            {inProgressCount > 0 && (
              <Text color={colors.status.info} bold>
                ◐ {inProgressCount}{' '}
              </Text>
            )}
            {todoCount > 0 && (
              <Text color={colors.text.dim}>
                ○ {todoCount}{' '}
              </Text>
            )}
            {blockedCount > 0 && (
              <Text color={colors.status.error} bold>
                ✖ {blockedCount}{' '}
              </Text>
            )}
            <Text color={percent === 100 ? colors.status.success : colors.status.info}>{progressBarStr} </Text>
            <Text color={colors.text.muted}>{percent}%</Text>
          </Box>

          {activeTask ? (
            <Box flexDirection="row" alignItems="center" flexShrink={1} marginLeft={1}>
              <Text color={colors.status.info} bold>
                {isRunning ? <LiveSpinner /> : '◐'} [CURRENT]{' '}
              </Text>
              <Text color={colors.text.bright} bold wrap="truncate-end">
                {activeTask.id}: {activeTask.title}
              </Text>
            </Box>
          ) : nextTask ? (
            <Box flexDirection="row" alignItems="center" flexShrink={1} marginLeft={1}>
              <Text color={colors.text.muted}>
                ○ [NEXT]{' '}
              </Text>
              <Text color={colors.text.muted} wrap="truncate-end">
                {nextTask.id}: {nextTask.title}
              </Text>
            </Box>
          ) : percent === 100 ? (
            <Text color={colors.status.success} bold>
              ✔ All complete
            </Text>
          ) : null}
        </Box>

        {/* Live sub-stage execution line when running */}
        {isRunning && activeActivity && (
          <Box flexDirection="row" alignItems="center" marginTop={0} paddingLeft={1}>
            <Text color={colors.status.accent} bold>
              ↳{' '}
            </Text>
            <Text color={colors.status.info}>
              <LiveSpinner />{' '}
            </Text>
            <Text color={colors.text.bright} wrap="truncate-end">
              {activeActivity.label}
            </Text>
            {typeof activeActivity.percent === 'number' && (
              <Text color={colors.text.dim}> ({activeActivity.percent}%)</Text>
            )}
          </Box>
        )}

        {/* Task items */}
        <Box flexDirection="column" marginTop={0}>
          {items.map((item: TodoItem) => (
            <Box key={item.id} flexDirection="column" width="100%">
              <Box flexDirection="row" width="100%" alignItems="center">
                <Box width={10} flexShrink={0}>
                  {renderStatusBadge(item.status)}
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
                {item.subtasks && item.subtasks.length > 0 && (
                  <Box marginLeft={1} flexShrink={0}>
                    <Text color={colors.text.dim}>
                      ({item.subtasks.filter((st) => st.status === 'done').length}/{item.subtasks.length})
                    </Text>
                  </Box>
                )}
                {item.priority && item.priority !== 'medium' && (
                  <Box marginLeft={1} flexShrink={0}>
                    <Text color={item.priority === 'high' ? colors.status.accent : colors.text.dim}>
                      [{item.priority}]
                    </Text>
                  </Box>
                )}
              </Box>
              {item.status === 'in_progress' && item.notes && (
                <Box marginLeft={14}>
                  <Text color={colors.text.dim} wrap="truncate-end">
                    └ Note: {item.notes}
                  </Text>
                </Box>
              )}
              {item.depends_on && item.depends_on.length > 0 && (
                <Box marginLeft={14}>
                  <Text color={colors.text.dim} wrap="truncate-end">
                    └ Depends on: {item.depends_on.join(', ')}
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
  },
);

PinnedTodoCard.displayName = 'PinnedTodoCard';
