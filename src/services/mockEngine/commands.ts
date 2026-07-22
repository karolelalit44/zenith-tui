import { LogItem, ThinkingState, OutputMeta } from '../../types';
import { MOCK_DIFF, BUILD_STEPS, MOCK_MESSAGES, FILE_EDIT_OUTPUT, PLUGIN_OUTPUT, BUILD_OUTPUT, THINKING_OUTPUT } from './data/mockResponses';

const delay = (ms: number, variance = 0.3): Promise<void> => {
  const varied = ms * (1 - variance + Math.random() * variance * 2);
  return new Promise(r => setTimeout(r, varied));
};

export const executeClearCommand = (): void => {
  console.clear();
};

export const executeAddDirCommand = async (
  input: string,
  onAddHistory: (item: LogItem) => void,
  onThinking?: (state: Partial<ThinkingState>) => void
): Promise<void> => {
  onThinking?.({ isActive: true, phase: 'scanning', message: 'Mapping directory structure...', steps: [
    { label: 'Scanning file system' },
    { label: 'Indexing files' },
    { label: 'Building context map' },
  ], currentStepIndex: 0 });
  await delay(600);

  onThinking?.({ currentStepIndex: 1, message: 'Indexing files...' });
  await delay(400);

  onThinking?.({ currentStepIndex: 2, message: 'Building context map...' });
  await delay(300);

  const parts = input.trim().split(' ');
  const path = parts.length > 1 ? parts[1] : '~/BCApps/new-module';

  onThinking?.({ isActive: false });
  onAddHistory({
    type: 'output',
    meta: {
      kind: 'file_created',
      icon: '✦',
      title: 'Workspace Synced',
      status: 'success',
      filePath: path,
      message: 'Directory mapped and vectorized. Zenith engine is now tracking this path.',
      elapsed: '1.3s',
    },
  });
};

export const executePluginCommand = async (
  onAddHistory: (item: LogItem) => void,
  onThinking?: (state: Partial<ThinkingState>) => void
): Promise<void> => {
  onThinking?.({ isActive: true, phase: 'fetching', message: 'Connecting to plugin registry...', steps: [
    { label: 'Connecting to registry' },
    { label: 'Verifying plugin status' },
  ], currentStepIndex: 0 });
  await delay(800);

  onThinking?.({ currentStepIndex: 1, message: 'Verifying plugin compatibility...' });
  await delay(500);

  onThinking?.({ isActive: false });
  onAddHistory({ type: 'output', meta: PLUGIN_OUTPUT });
};

export const executeBuildCommand = async (
  onAddHistory: (item: LogItem) => void,
  onThinking?: (state: Partial<ThinkingState>) => void
): Promise<void> => {
  onThinking?.({ isActive: true, phase: 'building', message: 'Initializing build pipeline...', steps: [
    { label: 'Resolving dependencies' },
    { label: 'Compiling TypeScript' },
    { label: 'Minifying assets' },
  ], currentStepIndex: 0 });
  await delay(800);

  onThinking?.({ currentStepIndex: 1, message: 'Compiling TypeScript sources...' });
  await delay(1200);

  onThinking?.({ currentStepIndex: 2, message: 'Minifying production assets...' });
  await delay(900);

  onThinking?.({ isActive: false });
  onAddHistory({ type: 'output', meta: BUILD_OUTPUT });
};

export const executeDefaultCommand = async (
  onAddHistory: (item: LogItem) => void,
  onThinking?: (state: Partial<ThinkingState>) => void
): Promise<void> => {
  const steps = [
    { label: 'Analyzing request' },
    { label: 'Determining tool trajectory' },
    { label: 'Executing update' },
  ];

  onThinking?.({ isActive: true, phase: 'thinking', message: 'Evaluating architectural constraints...', steps, currentStepIndex: 0 });
  await delay(600, 0.5);

  onThinking?.({ currentStepIndex: 1, phase: 'analyzing', message: 'Mapping code dependencies...' });
  await delay(1400, 0.4);

  onThinking?.({ currentStepIndex: 2, phase: 'tool_use', message: 'Patching source file...' });
  await delay(300);

  onThinking?.({ isActive: false });
  onAddHistory({ type: 'output', meta: FILE_EDIT_OUTPUT });
};
