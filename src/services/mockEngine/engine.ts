import { LogItem, ThinkingState } from '../../types';
import {
  executeClearCommand,
  executeAddDirCommand,
  executePluginCommand,
  executeBuildCommand,
  executeDefaultCommand,
} from './commands';

export const executeCommand = async (
  input: string,
  onAddHistory: (item: LogItem) => void,
  onResetHistory: () => void,
  onThinking?: (state: Partial<ThinkingState>) => void
): Promise<void> => {
  if (input.trim() === '/clear') {
    executeClearCommand();
    onResetHistory();
    return;
  }

  if (input.trim().startsWith('/add-dir')) {
    await executeAddDirCommand(input, onAddHistory, onThinking);
    return;
  }

  if (input.trim() === '/plugin') {
    await executePluginCommand(onAddHistory, onThinking);
    return;
  }

  if (input.trim() === '/settings') {
    return;
  }

  if (input.trim() === '/build') {
    await executeBuildCommand(onAddHistory, onThinking);
    return;
  }

  await executeDefaultCommand(onAddHistory, onThinking);
};
