import { APP_VERSION } from './app';

export const UI_CONTENT = {
  app: {
    title: 'ZENITH AI',
    subtitle: 'Terminal Agentic Coding Assistant',
    version: APP_VERSION,
    engineStatus: 'Online (Sonnet 3.7)',
    workspaceLabel: 'Workspace:',
    recentSessionsTitle: 'Recent Sessions',
  },
  statusBar: {
    idleText: 'Idle',
    processingText: 'Processing...',
    dirPrefix: 'dir:',
    cancelHint: 'esc cancel',
    commandsHint: '/ commands',
    modeHint: 'shift+m mode',
  },
  welcome: {
    tagline: 'Midday grind.',
    statusTitle: 'SYSTEM STATUS',
  },
  commands: [
    { command: '/mode', description: 'Switch active scenario mode (build | plan)' },
    { command: '/plan', description: 'Generate high-level architecture & project implementation plan' },
    { command: '/build', description: 'Execute code generation, test suites, and terminal build steps' },
    { command: '/clear', description: 'Clear active terminal workspace history' },
    { command: '/help', description: 'Display Zenith agent keyboard shortcuts and CLI command help' },
  ],
  export: {
    defaultPath: 'zenith_plans/implementation-plan.md',
  },
} as const;

export type UIContent = typeof UI_CONTENT;
