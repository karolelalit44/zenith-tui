export const SPACING = {
  /** Single line gap */
  xs: 0,
  /** Small gap (1 line) */
  sm: 1,
  /** Medium gap (2 lines) */
  md: 2,
  /** Large gap (3 lines) */
  lg: 3,
} as const;

export const PADDING = {
  /** No padding */
  none: 0,
  /** Standard horizontal padding */
  x: 1,
  /** Double horizontal padding */
  '2x': 2,
} as const;

export const BORDERS = {
  /** Single line border character */
  line: '─',
  /** Double line border character */
  double: '═',
  /** Round border character */
  round: '─',
} as const;

export const MAX_VISIBLE_EVENTS = 50;
export const TOOL_CALLS_PER_EVENT = 5;
export const MAX_PARAMETER_LENGTH = 80;
export const HISTORY_MAX_ENTRIES = 100;
export const NOTIFICATION_DURATION_MS = 3000;
