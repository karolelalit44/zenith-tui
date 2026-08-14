import { Box, Text } from 'ink';
import React from 'react';
import { useTerminalDimensions } from '../../../hooks/useTerminalDimensions';
import { useTheme } from '../../../theme/ThemeContext';
import type { TodoStatus } from '../../../types/scenario';
import type { ConsolidatedTodoBoard } from '../../../utils/todoBoard';

export const MAX_VISIBLE_TODOS = 10;

const SN_WIDTH = 7;
const STATUS_WIDTH = 12;

/**
 * A three-column table: serial number | todo title | status. The title is the
 * main, wider column and truncates to whatever space the terminal width allows;
 * status is one of success / failure / in progress (open items stay "todo").
 */
const STATUS_LABEL: Record<TodoStatus, string> = {
  todo: 'todo',
  in_progress: 'in progress',
  done: 'success',
  blocked: 'failure',
  cancelled: 'failure',
};

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

  const statusColor = (status: TodoStatus): string => {
    switch (status) {
      case 'done':
        return colors.status.success;
      case 'blocked':
      case 'cancelled':
        return colors.status.error;
      case 'in_progress':
        return colors.status.info;
      default:
        return colors.text.muted;
    }
  };

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
          items.map((item) => (
            <Box key={item.id} flexDirection="row" width="100%">
              <Box width={SN_WIDTH} flexShrink={0}>
                <Text color={colors.text.dim}>{item.id}</Text>
              </Box>
              <Box flexGrow={1} flexShrink={1}>
                <Text color={titleColor(item.status)} wrap="truncate-end">
                  {item.title}
                </Text>
              </Box>
              <Box width={STATUS_WIDTH} flexShrink={0} paddingLeft={1} alignItems="flex-end">
                <Text color={statusColor(item.status)} bold>
                  {STATUS_LABEL[item.status]}
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
