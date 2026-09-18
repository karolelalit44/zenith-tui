import { Box, Text } from 'ink';
import React from 'react';
import { useTerminalDimensions } from '../../../hooks/useTerminalDimensions';
import { useTheme } from '../../../theme/ThemeContext';
import type { TodoStatus } from '../../../types/scenario';
import type { ConsolidatedTodoBoard } from '../../../utils/todoBoard';
import { TODO_SN_WIDTH, TODO_STATUS_WIDTH, todoStatusColor, todoStatusSymbol } from './todoStatus';

export const MAX_VISIBLE_TODOS = 10;

/**
 * Strict three-column table: serial (1,2,3) | title (middle, bigger) |
 * status symbol only. No IDs, no status words, no extra per-row metadata.
 */

interface TodoBoardBlockProps {
  event: ConsolidatedTodoBoard;
  context?: { isRunning: boolean };
}

export const TodoBoardBlock: React.FC<TodoBoardBlockProps> = React.memo(({ event, context }) => {
  const { theme } = useTheme();
  const colors = theme.colors;
  const { columns } = useTerminalDimensions();
  const termCols = columns || process.stdout.columns || 80;
  const contentWidth = Math.max(30, termCols - 2);

  const all = event.board ?? [];
  const items = all.slice(0, MAX_VISIBLE_TODOS);
  const hidden = all.length - items.length;

  const titleColor = (status: TodoStatus): string =>
    status === 'done' || status === 'in_progress' ? colors.text.bright : colors.text.muted;

  return (
    <Box flexDirection="column" width={contentWidth} marginTop={1} marginBottom={1}>
      <Box
        flexDirection="column"
        backgroundColor={colors.code.background}
        borderStyle="round"
        borderColor={context?.isRunning ? colors.border.active : colors.border.muted}
        paddingX={1}
        paddingY={0}
      >
        <Text color={colors.text.bright} bold>
          TODO
        </Text>
        {items.length === 0 ? (
          <Text color={colors.text.dim}>(no todos yet)</Text>
        ) : (
          items.map((item, idx) => (
            <Box key={item.id} flexDirection="row" width="100%">
              <Box width={TODO_SN_WIDTH} flexShrink={0}>
                <Text color={colors.text.dim}>{String(idx + 1)}</Text>
              </Box>
              <Box flexGrow={1} flexShrink={1}>
                <Text color={titleColor(item.status)} wrap="truncate-end">
                  {item.title}
                </Text>
              </Box>
              <Box width={TODO_STATUS_WIDTH} flexShrink={0} paddingLeft={1}>
                <Text color={todoStatusColor(item.status, colors)} bold>
                  {todoStatusSymbol(item.status)}
                </Text>
              </Box>
            </Box>
          ))
        )}
        {hidden > 0 ? <Text color={colors.text.muted}>+{hidden} more…</Text> : null}
      </Box>
    </Box>
  );
});

TodoBoardBlock.displayName = 'TodoBoardBlock';
