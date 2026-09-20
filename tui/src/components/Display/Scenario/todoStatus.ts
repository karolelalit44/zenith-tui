import { Text } from 'ink';
import React from 'react';
import type { Theme } from '../../../theme/types';
import type { TodoStatus } from '../../../types/scenario';

/** Serial column width for the positional 1,2,3 numbers. */
export const TODO_SN_WIDTH = 4;

/** Status column width for the bracketed status glyph (e.g. [✓], [ ], [◐]). */
export const TODO_STATUS_WIDTH = 4;

const TODO_STATUS_SYMBOL: Record<TodoStatus, string> = {
  todo: '[ ]',
  in_progress: '[◐]',
  done: '[✓]',
  blocked: '[✗]',
  cancelled: '[✗]',
};

/**
 * Symbol for the status column. Unknown wire values (the transport casts
 * without an allowlist) fall back to pending [ ] so the cell never blanks.
 */
export function todoStatusSymbol(status: TodoStatus): string {
  return TODO_STATUS_SYMBOL[status] ?? '[ ]';
}

/** Color for the status symbol; unknown wire values fall back to dim. */
export function todoStatusColor(status: TodoStatus, colors: Theme['colors']): string {
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
}

export interface TodoStatusGlyphProps {
  status: TodoStatus;
  colors: Theme['colors'];
  bracketColor?: string;
  spinner?: React.ReactNode;
}

export const TodoStatusGlyph: React.FC<TodoStatusGlyphProps> = ({ status, colors, bracketColor, spinner }) => {
  const bColor = bracketColor ?? colors.text.dim;
  if (spinner) {
    return React.createElement(
      Text,
      null,
      React.createElement(Text, { color: bColor }, '['),
      React.createElement(Text, { color: colors.status.info, bold: true }, spinner),
      React.createElement(Text, { color: bColor }, ']'),
    );
  }

  const char =
    status === 'done'
      ? '✓'
      : status === 'in_progress'
        ? '◐'
        : status === 'blocked' || status === 'cancelled'
          ? '✗'
          : ' ';

  const charColor = todoStatusColor(status, colors);

  return React.createElement(
    Text,
    null,
    React.createElement(Text, { color: bColor }, '['),
    React.createElement(Text, { color: charColor, bold: status !== 'todo' }, char),
    React.createElement(Text, { color: bColor }, ']'),
  );
};
