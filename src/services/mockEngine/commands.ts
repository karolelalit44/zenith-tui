import { LogItem, DiffLine } from '../../types';
import { MOCK_DIFF, BUILD_MESSAGES, MOCK_MESSAGES } from './data/mockResponses';

const delay = (ms: number, variance = 0.3): Promise<void> => {
  const varied = ms * (1 - variance + Math.random() * variance * 2);
  return new Promise(r => setTimeout(r, varied));
};

export const executeClearCommand = (): LogItem[] => {
  console.clear();
  return [];
};

export const executeAddDirCommand = async (
  input: string,
  onLoading: (text: string) => void,
  onAddHistory: (item: LogItem) => void
): Promise<void> => {
  onLoading('Scanning file system...');
  await delay(800);

  const parts = input.trim().split(' ');
  const path = parts.length > 1 ? parts[1] : '~/BCApps/new-module';

  onAddHistory({ type: 'add-dir', path });
};

export const executePluginCommand = async (
  onLoading: (text: string) => void,
  onAddHistory: (item: LogItem) => void
): Promise<void> => {
  onLoading('Fetching registry...');
  await delay(1200);
  onAddHistory({ type: 'text', text: 'Plugin integration verified.' });
};

export const executeBuildCommand = async (
  onLoading: (text: string) => void,
  onAddHistory: (item: LogItem) => void
): Promise<void> => {
  onLoading('Initializing build system...');
  await delay(800);
  onAddHistory({ type: 'text', text: `  ✔ ${BUILD_MESSAGES.resolving} (142ms)` });

  onLoading('Compiling TypeScript...');
  await delay(1200);
  onAddHistory({ type: 'text', text: `  ✔ ${BUILD_MESSAGES.compiling} (1.1s)` });

  onLoading('Minifying assets...');
  await delay(900);
  onAddHistory({ type: 'text', text: `  ✔ ${BUILD_MESSAGES.minifying} (405ms)` });

  onAddHistory({ type: 'text', text: BUILD_MESSAGES.success });
};

export const executeDefaultCommand = async (
  onLoading: (text: string) => void,
  onAddHistory: (item: LogItem) => void
): Promise<void> => {
  onLoading('Thinking...');
  await delay(600, 0.5);
  onAddHistory({ type: 'text', text: MOCK_MESSAGES.thinking });

  onLoading('Using tool...');
  await delay(1400, 0.4);

  onAddHistory({
    type: 'tool',
    name: 'Update',
    args: 'src/engine.ts',
    resultTitle: MOCK_MESSAGES.toolResult,
    diff: MOCK_DIFF,
  });
};
