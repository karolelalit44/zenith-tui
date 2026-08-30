import type { KeybindId } from '../../config/keybind';
import type { OverlayType } from '../../hooks/useOverlayManager';
import type { ScenarioMode } from '../../types/scenario';

export type CommandCategory = 'Session' | 'View' | 'Mode' | 'Model' | 'Tools';

export interface CommandRunContext {
  openOverlay: (target: OverlayType) => void;
  clearTurns: () => void;
  clearTools: () => void;
  setMode: (mode: ScenarioMode) => void;
  openPalette?: () => void;
  toggleThinking?: () => void;
  toggleCalmMode?: () => void;
  savePlan?: () => void;
  triggerExit?: () => void;
  compactTurns?: () => void;
}

export interface CommandDef {
  id: string;

  slash?: string;

  title: string;
  description: string;
  category: CommandCategory;
  keybind?: KeybindId;
  keywords?: string[];
  hidden?: boolean;
  run: (ctx: CommandRunContext) => void;
}

/**
 * Single source of truth for both the `/` autocomplete and the ctrl+p command
 * palette.
 */
export const commandRegistry: CommandDef[] = [
  {
    id: 'help',
    slash: '/help',
    title: '/help',
    description: 'Show available commands & keyboard shortcuts',
    category: 'View',
    keybind: 'help',
    run: (ctx) => ctx.openOverlay('help'),
  },
  {
    id: 'settings',
    slash: '/settings',
    title: '/settings',
    description: 'Configure Zenith options and theme',
    category: 'View',
    run: (ctx) => ctx.openOverlay('settings'),
  },
  {
    id: 'context',
    slash: '/context',
    title: '/context',
    description: 'View the current file context window',
    category: 'View',
    run: (ctx) => ctx.openOverlay('context'),
  },
  {
    id: 'usage',
    slash: '/usage',
    title: '/usage',
    description: 'View token usage, costs, and budget',
    category: 'View',
    run: (ctx) => ctx.openOverlay('usage'),
  },
  {
    id: 'provider',
    slash: '/provider',
    title: '/provider',
    description: 'Manage AI provider configurations and active model',
    category: 'Model',
    run: (ctx) => ctx.openOverlay('provider'),
  },
  {
    id: 'clear',
    slash: '/clear',
    title: '/clear',
    description: 'Clear conversation and start a new chat',
    category: 'Session',
    keywords: ['new', 'reset', 'fresh', 'chat', 'session', 'clear'],
    run: (ctx) => ctx.clearTurns(),
  },
  {
    id: 'new',
    slash: '/new',
    title: '/new',
    description: 'Start a new chat session',
    category: 'Session',
    keywords: ['clear', 'reset', 'fresh', 'chat', 'session', 'new'],
    run: (ctx) => ctx.clearTurns(),
  },
  {
    id: 'clear_tools',
    slash: '/clear-tools',
    title: '/clear-tools',
    description: 'Remove tool output from the conversation history',
    category: 'Tools',
    run: (ctx) => ctx.clearTools(),
  },
  {
    id: 'compact',
    slash: '/compact',
    title: '/compact',
    description: 'Clear conversation history but keep a summary in context',
    category: 'Session',
    run: (ctx) => ctx.compactTurns?.(),
  },
  {
    id: 'build',
    slash: '/build',
    title: '/build',
    description: 'Switch to Build mode',
    category: 'Mode',
    run: (ctx) => ctx.setMode('build'),
  },
  {
    id: 'plan',
    slash: '/plan',
    title: '/plan',
    description: 'Switch to Plan mode',
    category: 'Mode',
    run: (ctx) => ctx.setMode('plan'),
  },
  {
    id: 'toggle_thinking',
    title: 'Toggle thinking',
    description: 'Collapse or expand reasoning blocks',
    category: 'View',
    keybind: 'thinking',
    run: (ctx) => ctx.toggleThinking?.(),
  },
  {
    id: 'calm_mode',
    slash: '/calm',
    title: '/calm',
    description: 'Calm mode — toggle hiding model thinking output (persisted)',
    category: 'View',
    keywords: ['calm', 'quiet', 'hide', 'thinking'],
    run: (ctx) => ctx.toggleCalmMode?.(),
  },
  {
    id: 'switch_mode',
    title: 'Switch mode',
    description: 'Choose Build or Plan mode',
    category: 'Mode',
    keybind: 'mode',
    run: (ctx) => ctx.openOverlay('mode'),
  },
  {
    id: 'save_plan',
    title: 'Save plan to file',
    description: 'Write the latest plan to disk',
    category: 'Tools',
    keybind: 'save_plan',
    run: (ctx) => ctx.savePlan?.(),
  },
  {
    id: 'clear_conversation',
    title: 'Clear conversation',
    description: 'Reset conversation and start a new chat',
    category: 'Session',
    keybind: 'clear_turns',
    run: (ctx) => ctx.clearTurns(),
  },
  {
    id: 'new_chat',
    title: 'New chat',
    description: 'Start a new chat session',
    category: 'Session',
    keywords: ['clear', 'reset', 'fresh', 'session'],
    run: (ctx) => ctx.clearTurns(),
  },
  {
    id: 'command_palette',
    title: 'Command palette',
    description: 'Open this palette',
    category: 'View',
    keybind: 'palette',
    hidden: true,
    run: (ctx) => ctx.openPalette?.(),
  },
  {
    id: 'session',
    slash: '/session',
    title: '/session',
    description: 'Browse and resume previous sessions',
    category: 'Session',
    keywords: ['history', 'resume', 'previous', 'conversations'],
    run: (ctx) => ctx.openOverlay('session'),
  },
  {
    id: 'exit',
    slash: '/exit',
    title: '/exit',
    description: 'Save session and exit Zenith gracefully',
    category: 'Session',
    keywords: ['quit', 'close', 'goodbye', 'bye'],
    run: (ctx) => ctx.triggerExit?.(),
  },
];

export function dispatchCommand(rawInput: string, ctx: CommandRunContext): boolean {
  const trimmed = rawInput.trim().toLowerCase();
  const def = commandRegistry.find((c) => c.slash && c.slash.toLowerCase() === trimmed);
  if (!def) return false;
  def.run(ctx);
  return true;
}
