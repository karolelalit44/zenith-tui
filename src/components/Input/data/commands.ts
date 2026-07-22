import { CommandHint } from '../../../types';

export const COMMAND_LIST: CommandHint[] = [
  { command: '/add-dir', description: 'Add a new working directory' },
  { command: '/agents', description: 'Manage agent configurations' },
  { command: '/clear', description: 'Clear conversation history (reset, new) and free up context' },
  { command: '/compact', description: 'Clear conversation history but keep a summary in context' },
  { command: '/context', description: 'View the current file context window' },
  { command: '/help', description: 'Show available commands' },
  { command: '/persona', description: 'Switch the active agent persona' },
  { command: '/plugin', description: 'Manage Zenith plugins and extensions' },
  { command: '/settings', description: 'Configure Zenith options and theme' },
];
