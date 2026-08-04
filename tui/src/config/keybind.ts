import type { Key } from 'ink';

export type KeybindId =
  | 'submit'
  | 'newline'
  | 'history_up'
  | 'history_down'
  | 'help'
  | 'mode'
  | 'palette'
  | 'thinking'
  | 'save_plan'
  | 'clear_turns'
  | 'clear_input'
  | 'interrupt'
  | 'model_picker';

export interface Keybinding {
  keys: string[];
  description: string;
}

export type KeybindingMap = Record<KeybindId, Keybinding>;

export const KEYBINDINGS: KeybindingMap = {
  submit: { keys: ['enter'], description: 'Send message' },
  newline: { keys: ['shift+return', 'ctrl+return', 'ctrl+j'], description: 'Insert newline' },
  history_up: { keys: ['up'], description: 'Previous prompt (cursor at start)' },
  history_down: { keys: ['down'], description: 'Next prompt (cursor at end)' },
  help: { keys: ['?'], description: 'Help (empty input)' },
  mode: { keys: ['shift+m'], description: 'Switch mode (empty input)' },
  palette: { keys: ['ctrl+p'], description: 'Command palette' },
  thinking: { keys: ['ctrl+t', 'shift+t'], description: 'Toggle thinking' },
  save_plan: { keys: ['ctrl+s'], description: 'Save plan to file' },
  clear_turns: { keys: ['ctrl+l'], description: 'Clear conversation' },
  clear_input: { keys: ['ctrl+c'], description: 'Clear input / cancel run' },
  interrupt: { keys: ['escape'], description: 'Cancel running / close' },
  model_picker: { keys: ['ctrl+e'], description: 'Switch provider/model' },
};

export type InkKeyLike = Pick<
  Key,
  | 'upArrow'
  | 'downArrow'
  | 'leftArrow'
  | 'rightArrow'
  | 'pageDown'
  | 'pageUp'
  | 'home'
  | 'end'
  | 'return'
  | 'escape'
  | 'ctrl'
  | 'shift'
  | 'tab'
  | 'backspace'
  | 'delete'
  | 'meta'
>;

const NAMED_KEYS: Record<string, keyof InkKeyLike> = {
  enter: 'return',
  return: 'return',
  esc: 'escape',
  escape: 'escape',
  up: 'upArrow',
  down: 'downArrow',
  left: 'leftArrow',
  right: 'rightArrow',
  pageup: 'pageUp',
  pagedown: 'pageDown',
  home: 'home',
  end: 'end',
  tab: 'tab',
  backspace: 'backspace',
  delete: 'delete',
};

const DISPLAY_NAMES: Record<string, string> = {
  enter: 'Enter',
  return: 'Enter',
  esc: 'Esc',
  escape: 'Esc',
  up: '\u2191',
  down: '\u2193',
  left: '\u2190',
  right: '\u2192',
  pageup: 'PgUp',
  pagedown: 'PgDn',
  home: 'Home',
  end: 'End',
  tab: 'Tab',
  backspace: '\u232b',
  delete: 'Del',
};

interface ParsedSpec {
  mods: { ctrl: boolean; shift: boolean; meta: boolean };
  primary: string;
}

function parseSpec(spec: string): ParsedSpec {
  const parts = spec.split('+');
  const mods = { ctrl: false, shift: false, meta: false };
  for (const part of parts.slice(0, -1)) {
    const mod = part.trim().toLowerCase();
    if (mod === 'ctrl' || mod === 'control') mods.ctrl = true;
    else if (mod === 'shift') mods.shift = true;
    else if (mod === 'meta' || mod === 'cmd' || mod === 'command') mods.meta = true;
  }
  return { mods, primary: parts[parts.length - 1].trim().toLowerCase() };
}

function specMatches(input: string, key: InkKeyLike, spec: string): boolean {
  const { mods, primary } = parseSpec(spec);

  if (mods.ctrl && !key.ctrl) return false;
  if (mods.shift && !key.shift) return false;
  if (mods.meta && !key.meta) return false;

  if (primary in NAMED_KEYS) {
    const field = NAMED_KEYS[primary];
    if (!key[field]) return false;

    if (!mods.ctrl && key.ctrl) return false;
    if (!mods.shift && key.shift) return false;
    if (!mods.meta && key.meta) return false;
    return true;
  }

  if (primary.length !== 1) return false;

  if (input === primary || input === primary.toUpperCase() || input === primary.toLowerCase()) {
    return true;
  }

  if (mods.ctrl && /^[a-z]$/.test(primary)) {
    const control = String.fromCharCode(primary.charCodeAt(0) - 96);
    if (input === control || input === '') return true;
  }

  return false;
}

export function matchKeypress(input: string, key: InkKeyLike, bindings: KeybindingMap = KEYBINDINGS): KeybindId[] {
  const matched: KeybindId[] = [];
  for (const id of Object.keys(bindings) as KeybindId[]) {
    for (const spec of bindings[id].keys) {
      if (specMatches(input, key, spec)) {
        matched.push(id);
        break;
      }
    }
  }
  return matched;
}

export function formatKeySpec(spec: string): string {
  const { mods, primary } = parseSpec(spec);
  const parts: string[] = [];
  if (mods.ctrl) parts.push('Ctrl');
  if (mods.shift) parts.push('Shift');
  if (mods.meta) parts.push('Meta');
  parts.push(DISPLAY_NAMES[primary] ?? (primary.length === 1 ? primary.toUpperCase() : primary));
  return parts.join('+');
}

export function formatKeyBind(id: KeybindId, bindings: KeybindingMap = KEYBINDINGS): string {
  const spec = bindings[id]?.keys[0];
  return spec ? formatKeySpec(spec) : '';
}
