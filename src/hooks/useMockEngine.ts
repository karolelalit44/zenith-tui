import { useState, useCallback } from 'react';
import { LogItem } from '../types';
import { executeCommand as engineExecuteCommand } from '../services/mockEngine';

export function useMockEngine() {
  const [history, setHistory] = useState<LogItem[]>([]);
  const [isExecuting, setIsExecuting] = useState(false);
  const [loadingText, setLoadingText] = useState('');

  const executeCommand = useCallback(async (input: string) => {
    setIsExecuting(true);
    setHistory(prev => [...prev, { type: 'user', text: input }]);

    const onLoading = (text: string) => setLoadingText(text);
    const onAddHistory = (item: LogItem) => setHistory(prev => [...prev, item]);
    const onResetHistory = () => {
      setHistory([]);
      setIsExecuting(false);
    };

    await engineExecuteCommand(input, onLoading, onAddHistory, onResetHistory);

    if (input.trim() !== '/clear' && input.trim() !== '/settings') {
      setIsExecuting(false);
    }
  }, []);

  return { history, isExecuting, loadingText, executeCommand };
}
