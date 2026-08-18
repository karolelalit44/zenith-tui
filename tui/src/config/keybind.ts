import type { KeyBinding } from '@inkjs/ui';

export type KeybindScheme = 'default' | 'vim';

export interface KeybindAction {
  id: string;
  description: string;
  keys: string[];
}

export const keybindActions: KeybindAction[] = [
  // Navigation
  { id: 'up', description: 'Move up', keys: ['up', 'k'] },
  { id: 'down', description: 'Move down', keys: ['down', 'j'] },
  { id: 'left', description: 'Move left', keys: ['left', 'h'] },
  { id: 'right', description: 'Move right', keys: ['right', 'l'] },
  { id: 'pageUp', description: 'Page up', keys: ['pageup', 'ctrl+u'] },
  { id: 'pageDown', description: 'Page down', keys: ['pagedown', 'ctrl+d'] },
  { id: 'home', description: 'Go to top', keys: ['home', 'gg'] },
  { id: 'end', description: 'Go to bottom', keys: ['end', 'G'] },

  // Selection
  { id: 'select', description: 'Select item', keys: ['enter', 'space'] },
  { id: 'selectAll', description: 'Select all', keys: ['ctrl+a'] },
  { id: 'deselect', description: 'Deselect', keys: ['escape'] },
  { id: 'toggleSelect', description: 'Toggle selection', keys: ['ctrl+space'] },

  // Actions
  { id: 'confirm', description: 'Confirm', keys: ['enter'] },
  { id: 'cancel', description: 'Cancel/Close', keys: ['escape', 'q'] },
  { id: 'delete', description: 'Delete', keys: ['delete', 'd', 'x'] },
  { id: 'edit', description: 'Edit', keys: ['e', 'enter'] },
  { id: 'new', description: 'Create new', keys: ['n'] },
  { id: 'copy', description: 'Copy', keys: ['ctrl+c', 'y'] },
  { id: 'paste', description: 'Paste', keys: ['ctrl+v', 'p'] },
  { id: 'cut', description: 'Cut', keys: ['ctrl+x', 'dd'] },

  // Search/Filter
  { id: 'search', description: 'Search', keys: ['/', 'ctrl+f'] },
  { id: 'clearSearch', description: 'Clear search', keys: ['escape', 'ctrl+l'] },
  { id: 'nextMatch', description: 'Next match', keys: ['n', 'enter'] },
  { id: 'prevMatch', description: 'Previous match', keys: ['N', 'shift+enter'] },

  // Tabs/Panels
  { id: 'nextTab', description: 'Next tab', keys: ['tab', 'gt', 'ctrl+tab'] },
  { id: 'prevTab', description: 'Previous tab', keys: ['shift+tab', 'gT', 'ctrl+shift+tab'] },
  { id: 'closeTab', description: 'Close tab', keys: ['ctrl+w', 'c'] },
  { id: 'splitHorizontal', description: 'Split horizontal', keys: ['ctrl+s', 's'] },
  { id: 'splitVertical', description: 'Split vertical', keys: ['ctrl+v', 'v'] },
  { id: 'focusNext', description: 'Focus next panel', keys: ['ctrl+j', 'ctrl+right'] },
  { id: 'focusPrev', description: 'Focus previous panel', keys: ['ctrl+k', 'ctrl+left'] },

  // Commands
  { id: 'commandPalette', description: 'Command palette', keys: ['ctrl+p', ':'] },
  { id: 'quickOpen', description: 'Quick open', keys: ['ctrl+o'] },
  { id: 'settings', description: 'Open settings', keys: ['ctrl+,', ','] },

  // Help
  { id: 'help', description: 'Show help', keys: ['?', 'f1'] },
  { id: 'keybindings', description: 'Show keybindings', keys: ['ctrl+k', 'ctrl+k'] },

  // Vim-specific
  { id: 'enterNormalMode', description: 'Enter normal mode', keys: ['escape'] },
  { id: 'enterInsertMode', description: 'Enter insert mode', keys: ['i', 'a', 'o', 'O'] },
  { id: 'enterVisualMode', description: 'Enter visual mode', keys: ['v', 'V', 'ctrl+v'] },
  { id: 'repeat', description: 'Repeat last action', keys: ['.'] },
  { id: 'undo', description: 'Undo', keys: ['u'] },
  { id: 'redo', description: 'Redo', keys: ['ctrl+r'] },
];

const defaultKeybindings: Record<string, string[]> = {};
const vimKeybindings: Record<string, string[]> = {};

for (const action of keybindActions) {
  defaultKeybindings[action.id] = [action.keys[0]];
  vimKeybindings[action.id] = action.keys.filter((k) => !['enter', 'space', 'escape', 'tab', 'shift+tab', 'ctrl+a', 'ctrl+c', 'ctrl+v', 'ctrl+x', 'ctrl+f', 'ctrl+p', 'ctrl+o', 'ctrl+,', 'ctrl+w', 'ctrl+s', 'ctrl+j', 'ctrl+k', 'ctrl+l', 'ctrl+r', 'ctrl+u', 'ctrl+d', 'ctrl+tab', 'ctrl+shift+tab', 'pageup', 'pagedown', 'home', 'end', 'delete', 'up', 'down', 'left', 'right', 'f1', '?'].includes(k));
}

export const keybindSchemes: Record<KeybindScheme, Record<string, string[]>> = {
  default: defaultKeybindings,
  vim: vimKeybindings,
};

export function getKeybindings(scheme: KeybindScheme): Record<string, string[]> {
  return keybindSchemes[scheme] ?? keybindSchemes.default;
}

export function getKeyForAction(scheme: KeybindScheme, actionId: string): string[] {
  return keybindSchemes[scheme]?.[actionId] ?? keybindSchemes.default[actionId] ?? [];
}

export function formatKey(key: string): string {
  return key
    .split('+')
    .map((part) => part.toUpperCase())
    .join('+');
}

export function matchesKeybinding(scheme: KeybindScheme, actionId: string, input: string): boolean {
  const keys = getKeyForAction(scheme, actionId);
  return keys.some((k) => k.toLowerCase() === input.toLowerCase());
}