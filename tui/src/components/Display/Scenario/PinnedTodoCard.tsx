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
const SN_WIDTH = 4;
const STATUS_WIDTH = 3;

/**
 * Strict three-column rows: serial (1,2,3) | title (middle, bigger) |
 * status symbol only (○ pending · ◐ active · ✔ done · ✖ blocked/cancelled).
 */

const STATUS_SYMBOL: Record<TodoStatus, string> = {
  todo: '○',
  in_progress: '◐',
  done: '✔',
  blocked: '✖',
  cancelled: '✖',
};

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
    const totalCount = all.length;
    const percent = totalCount > 0 ? Math.round((doneCount / totalCount) * 100) : 0;

    // Build progress bar: e.g. [██████░░░░]
    const clampedPercent = Math.max(0, Math.min(100, percent));
    const rawFilled = Math.round((clampedPercent / 100) * PROGRESS_BAR_WIDTH);
    const filledWidth = Math.max(0, Math.min(PROGRESS_BAR_WIDTH, rawFilled));
    const emptyWidth = PROGRESS_BAR_WIDTH - filledWidth;
    const progressBarStr = `[${'█'.repeat(filledWidth)}${'░'.repeat(emptyWidth)}]`;

    // Limit visible items to MAX_PINNED_TODOS
    const items = all.slice(0, MAX_PINNED_TODOS);
    const hiddenCount = all.length - items.length;

    const statusColor = (status: TodoStatus): string => {
      switch (status) {
        case 'done':
          return colors.status.success;
        case 'in_progress':
          return colors.status.info;
        case 'blocked':
        case 'cancelled':
          return colors.status.error;
        default:
          return colors.text.dim;
      }
    };

    const renderStatusSymbol = (status: TodoStatus) => {
      if (status === 'in_progress' && isRunning) {
        return (
          <Text color={colors.status.info} bold>
            <LiveSpinner />
          </Text>
        );
      }
      return (
        <Text color={statusColor(status)} bold={status !== 'todo'}>
          {STATUS_SYMBOL[status]}
        </Text>
      );
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
        {/* Header row: title + progress */}
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

          {percent === 100 ? (
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

        {/* Task rows: serial | title | status symbol only */}
        <Box flexDirection="column" marginTop={0}>
          {items.map((item: TodoItem, idx: number) => (
            <Box key={item.id} flexDirection="row" width="100%" alignItems="center">
              <Box width={SN_WIDTH} flexShrink={0}>
                <Text color={colors.text.dim}>{String(idx + 1)}</Text>
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
              <Box width={STATUS_WIDTH} flexShrink={0} paddingLeft={1}>
                {renderStatusSymbol(item.status)}
              </Box>
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
