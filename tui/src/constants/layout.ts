/**
 * Shared layout constants for the TUI. Single source of truth for the
 * conversation gutter, content widths and the composer footer inset so
 * every row stays on the same rail without hand-synced magic numbers.
 */

/** Horizontal padding applied to the outside of every long-form conversation row. */
export const CONTENT_PAD_X = 1;

/** Inset subtracted from the terminal width to get the usable row width (App container paddingX). */
export const CONTENT_WIDTH_INSET = 2;

/** Width inset used inside bordered widgets (tables, code blocks) relative to terminal width. */
export const TABLE_WIDTH_INSET = 6;

/** Right-side inset used by the composer footer row. */
export const FOOTER_EDGE_PAD = 6;

/** Nested content rail: rows inside a conversation block start at CONTENT_PAD_X + NESTED_PAD_X. */
export const NESTED_PAD_X = 2;

/** Uniform vertical gap (blank line) between conversation rows. */
export const ROW_GAP = 1;

/** Usable row width for a given terminal width, clamped to a minimum. */
export function contentWidth(columns: number, inset: number = CONTENT_WIDTH_INSET): number {
  return Math.max(30, columns - inset);
}
