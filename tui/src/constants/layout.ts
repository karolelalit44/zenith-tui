export const SPACING = {
  xs: 0,

  sm: 1,

  md: 2,

  lg: 3,
} as const;

export const PADDING = {
  none: 0,

  x: 1,

  '2x': 2,
} as const;

export const BORDERS = {
  line: '─',

  double: '═',

  round: '─',
} as const;

export const MAX_VISIBLE_EVENTS = 50;
export const TOOL_CALLS_PER_EVENT = 5;
export const MAX_PARAMETER_LENGTH = 80;
export const HISTORY_MAX_ENTRIES = 100;
export const NOTIFICATION_DURATION_MS = 3000;
