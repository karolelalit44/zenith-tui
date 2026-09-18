import type { Theme } from '../../../theme/types';
import type { TodoStatus } from '../../../types/scenario';

/** Serial column width for the positional 1,2,3 numbers. */
export const TODO_SN_WIDTH = 4;

/** Status column width for the single symbol glyph. */
export const TODO_STATUS_WIDTH = 3;

const TODO_STATUS_SYMBOL: Record<TodoStatus, string> = {
  todo: '○',
  in_progress: '◐',
  done: '✔',
  blocked: '✖',
  cancelled: '✖',
};

/**
 * Symbol for the status column. Unknown wire values (the transport casts
 * without an allowlist) fall back to pending ○ so the cell never blanks.
 *
 * Font note: ○ U+25CB · ◐ U+25D0 · ✔ U+2714 · ✖ U+2716 need a patched or
 * recent Windows Terminal / Ghostty / Alacritty font; missing glyphs show
 * tofu, so verify on targets before swapping symbols.
 */
export function todoStatusSymbol(status: TodoStatus): string {
  return TODO_STATUS_SYMBOL[status] ?? '○';
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
