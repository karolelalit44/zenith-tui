import { DiffLine } from '../../../types';

export const MOCK_DIFF: DiffLine[] = [
  { type: 'context', number: 1, segments: [{ text: '  function ZenithEngine() {' }] },
  { type: 'remove', number: 2, segments: [{ text: '    const state = ', isHighlightedWord: false }, { text: '"mock"', isHighlightedWord: true }, { text: ';' }] },
  { type: 'add', number: 2, segments: [{ text: '    const state = ', isHighlightedWord: false }, { text: '"simulated"', isHighlightedWord: true }, { text: ';' }] },
  { type: 'context', number: 3, segments: [{ text: '  }' }] },
];

export const BUILD_MESSAGES = {
  resolving: 'Resolving dependencies',
  compiling: 'Compiling TypeScript',
  minifying: 'Minifying assets',
  success: '✨ Build successful in 1.6s',
} as const;

export const MOCK_MESSAGES = {
  thinking: 'Analyzing architectural constraints and determining tool trajectory.',
  toolResult: 'File patched automatically.',
  pluginResult: 'Plugin integration verified.',
} as const;
