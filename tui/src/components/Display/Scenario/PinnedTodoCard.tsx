import { Box, Text } from 'ink';
import React from 'react';
import { useAnimationTick } from '../../../context/AnimationContext';
import { useTerminalDimensions } from '../../../hooks/useTerminalDimensions';
import { useTheme } from '../../../theme/ThemeContext';
import type { TodoItem, TodoStatus } from '../../../types/scenario';
import type { ConsolidatedTodoBoard } from '../../../utils/todoBoard';
import { TODO_SN_WIDTH, TODO_STATUS_WIDTH, TodoStatusGlyph } from './todoStatus';

const SPINNER_FRAMES = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'];
const MAX_PINNED_TODOS = 5;
const PROGRESS_BAR_WIDTH = 8;

const LiveSpinner: React.FC = () => {
  const tick = useAnimationTick();
  return <Text>{SPINNER_FRAMES[tick % SPINNER_FRAMES.length]}</Text>;
};

export interface PinnedTodoCardProps {
  event: ConsolidatedTodoBoard;
  isRunning?: boolean;
  activeActivity?: {
    label: string;
    percent?: number;
  };
}

export const PinnedTodoCard: React.FC<PinnedTodoCardProps> = React.memo(
  ({ event, isRunning = false, activeActivity }) => {
    const { theme } = useTheme();
    const colors = theme.colors;
    const { columns } = useTerminalDimensions();
    const termCols = columns || process.stdout.columns || 80;
    const contentWidth = Math.max(30, termCols - 2);

    const pending = event.pending === true;

    const all = event.board ?? [];
    if (all.length === 0) return null;

    // When pending, no items are truly confirmed — show 0% to avoid
    // false-completeness (the requested statuses are NOT tool-verified).
    const doneCount = pending ? 0 : all.filter((t) => t.status === 'done').length;
    const totalCount = all.length;
    const percent = totalCount > 0 ? Math.round((doneCount / totalCount) * 100) : 0;

    // Build progress bar: e.g. [██████░░░░]
    const clampedPercent = Math.max(0, Math.min(100, percent));
    const rawFilled = Math.round((clampedPercent / 100) * PROGRESS_BAR_WIDTH);
    const filledWidth = Math.max(0, Math.min(PROGRESS_BAR_WIDTH, rawFilled));
    const emptyWidth = PROGRESS_BAR_WIDTH - filledWidth;

    // Limit visible items to MAX_PINNED_TODOS
    const items = all.slice(0, MAX_PINNED_TODOS);
    const hiddenCount = all.length - items.length;

    const borderColor = isRunning ? colors.border.active : colors.border.muted;
    const bracketColor = colors.status.warning;

    const countStr = `(${doneCount}/${totalCount})`;
    const fullSuffix = pending ? ' · awaiting tool result' : '';
    // Only show full suffix when terminal has enough room (>= 60 cols) to prevent wrapping
    const statusSuffix = contentWidth >= 60 ? fullSuffix : '';
    const percentStr = `${percent}%${statusSuffix}`;

    const leftWidth = 9 + countStr.length; // '╭─ ' (3) + 'Todo ' (5) + countStr + ' ' (1)
    const rightWidth = 7 + PROGRESS_BAR_WIDTH + percentStr.length; // ' [' (2) + bar (PROGRESS_BAR_WIDTH) + '] ' (2) + percentStr + ' ─╮' (3)
    const ruleWidth = Math.max(0, contentWidth - leftWidth - rightWidth);

    const getTitleColor = (status: TodoStatus): string => {
      if (pending) return colors.text.muted;
      switch (status) {
        case 'blocked':
        case 'cancelled':
          return colors.status.error;
        default:
          return colors.text.bright;
      }
    };

    return (
      <Box flexDirection="column" width={contentWidth}>
        {/* Top border with embedded title, ratio, horizontal rule, progress bar, and percentage */}
        <Box flexDirection="row" width={contentWidth} backgroundColor={colors.code.background}>
          <Box flexShrink={0}>
            <Text color={borderColor}>╭─ </Text>
            <Text color={colors.text.bright} bold>
              Todo{' '}
            </Text>
            <Text color={bracketColor} bold>
              {countStr}
            </Text>
            <Text color={borderColor}> </Text>
          </Box>
          <Box flexGrow={1} flexShrink={1} overflow="hidden">
            <Text color={borderColor} wrap="truncate-end">
              {'─'.repeat(ruleWidth)}
            </Text>
          </Box>
          <Box flexShrink={0}>
            <Text color={borderColor}> </Text>
            <Text color={bracketColor}>[</Text>
            <Text color={colors.text.bright}>{'█'.repeat(filledWidth)}</Text>
            <Text color={colors.text.dim}>{'░'.repeat(emptyWidth)}</Text>
            <Text color={bracketColor}>] </Text>
            <Text color={colors.text.bright}>{percentStr}</Text>
            <Text color={borderColor}> ─╮</Text>
          </Box>
        </Box>

        {/* Box body: left & right borders, bottom border with rounded corners */}
        <Box
          flexDirection="column"
          width={contentWidth}
          backgroundColor={colors.code.background}
          borderStyle="round"
          borderTop={false}
          borderColor={borderColor}
          paddingX={1}
          paddingY={0}
        >
          {/* Live sub-stage execution line when running (hidden while pending) */}
          {isRunning && activeActivity && !pending && (
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
                <Box width={TODO_SN_WIDTH} flexShrink={0}>
                  <Text color={colors.text.bright}>{String(idx + 1)}</Text>
                </Box>
                <Box flexGrow={1} flexShrink={1}>
                  <Text
                    color={getTitleColor(item.status)}
                    bold={item.status === 'in_progress' && !pending}
                    wrap="truncate-end"
                  >
                    {item.title}
                  </Text>
                </Box>
                <Box width={TODO_STATUS_WIDTH} flexShrink={0} paddingLeft={1}>
                  <TodoStatusGlyph
                    status={pending ? 'todo' : item.status}
                    colors={colors}
                    bracketColor={bracketColor}
                    spinner={!pending && item.status === 'in_progress' && isRunning ? <LiveSpinner /> : undefined}
                  />
                </Box>
              </Box>
            ))}
          </Box>

          {hiddenCount > 0 && (
            <Box marginTop={0}>
              <Text color={colors.text.dim}>+{hiddenCount} more todos…</Text>
            </Box>
          )}
        </Box>
      </Box>
    );
  },
);

PinnedTodoCard.displayName = 'PinnedTodoCard';
