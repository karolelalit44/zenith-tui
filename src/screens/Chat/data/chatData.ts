export const CHAT_DATA = {
  emptyState: {
    message: 'No conversation history.',
  },
  userPrefix: '> ',
  toolPrefix: '● ',
  loadingFooter: {
    interruptHint: ' (esc to interrupt)',
  },
  modeFooter: {
    autoAcceptText: '▸▸ auto-accept edits on',
    cycleHint: ' (shift+tab to cycle)',
  },
} as const;
