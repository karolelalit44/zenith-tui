export const UI_CONSTANTS = {
  BOX_BORDER_CHARS: {
    topLeft: '╭',
    topRight: '╮',
    top: '═',
    bottom: '═',
    bottomLeft: '╰',
    bottomRight: '╯',
    left: '║',
    right: '║',
  } as Record<string, string>,
  DIVIDER_CHAR: '║',
  SEPARATOR_WIDTH: 100,
  AUTOCOMPLETE_COMMAND_WIDTH: 25,
  LINE_NUMBER_WIDTH: 6,
} as const;
