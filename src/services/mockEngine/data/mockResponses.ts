import { DiffLine, OutputMeta } from '../../../types';

export const MOCK_DIFF: DiffLine[] = [
  { type: 'context', number: 1, segments: [{ text: '  function ZenithEngine() {' }] },
  { type: 'remove', number: 2, segments: [{ text: '    const state = ', isHighlightedWord: false }, { text: '"mock"', isHighlightedWord: true }, { text: ';' }] },
  { type: 'add', number: 2, segments: [{ text: '    const state = ', isHighlightedWord: false }, { text: '"simulated"', isHighlightedWord: true }, { text: ';' }] },
  { type: 'context', number: 3, segments: [{ text: '  }' }] },
];

export const BUILD_STEPS = [
  { label: 'Resolving dependencies', duration: '142ms', success: true },
  { label: 'Compiling TypeScript', duration: '1.1s', success: true },
  { label: 'Minifying assets', duration: '405ms', success: true },
];

export const MOCK_MESSAGES = {
  thinking: 'Analyzing architectural constraints and determining tool trajectory.',
  pluginResult: 'Plugin integration verified.',
} as const;

export const FILE_EDIT_OUTPUT: OutputMeta = {
  kind: 'file_edit',
  icon: '✎',
  title: 'File Updated',
  status: 'success',
  filePath: 'src/engine.ts',
  message: 'File patched automatically.',
  diff: MOCK_DIFF,
  elapsed: '1.4s',
};

export const PLUGIN_OUTPUT: OutputMeta = {
  kind: 'tool_result',
  icon: '◆',
  title: 'Plugin Verified',
  status: 'success',
  message: MOCK_MESSAGES.pluginResult,
  elapsed: '1.2s',
};

export const BUILD_OUTPUT: OutputMeta = {
  kind: 'build_result',
  icon: '⬡',
  title: 'Build Complete',
  status: 'success',
  buildSteps: BUILD_STEPS,
  elapsed: '1.6s',
};

export const THINKING_OUTPUT: OutputMeta = {
  kind: 'message',
  icon: '●',
  title: 'Analysis',
  status: 'info',
  message: MOCK_MESSAGES.thinking,
};
