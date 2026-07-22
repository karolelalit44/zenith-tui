import { LogItem } from '../../types';
import {
  executeClearCommand,
  executeAddDirCommand,
  executePluginCommand,
  executeBuildCommand,
  executeDefaultCommand,
} from './commands';

export const executeCommand = async (
  input: string,
  onLoading: (text: string) => void,
  onAddHistory: (item: LogItem) => void,
  onResetHistory: () => void
): Promise<void> => {
  if (input.trim() === '/clear') {
    executeClearCommand();
    onResetHistory();
    return;
  }

  if (input.trim().startsWith('/add-dir')) {
    await executeAddDirCommand(input, onLoading, onAddHistory);
    return;
  }

  if (input.trim() === '/plugin') {
    await executePluginCommand(onLoading, onAddHistory);
    return;
  }

  if (input.trim() === '/settings') {
    return;
  }

  if (input.trim() === '/build') {
    await executeBuildCommand(onLoading, onAddHistory);
    return;
  }

  await executeDefaultCommand(onLoading, onAddHistory);
};
