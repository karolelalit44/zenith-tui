import { useState, useCallback } from 'react';
import { LogItem, ThinkingState } from '../types';
import { executeCommand as engineExecuteCommand } from '../services/mockEngine';

const initialThinkingState: ThinkingState = {
  isActive: false,
  phase: 'idle',
  message: '',
  steps: [],
  currentStepIndex: 0,
};

export function useMockEngine() {
  const [history, setHistory] = useState<LogItem[]>([]);
  const [isExecuting, setIsExecuting] = useState(false);
  const [thinking, setThinking] = useState<ThinkingState>(initialThinkingState);

  const executeCommand = useCallback(async (input: string) => {
    setIsExecuting(true);
    setHistory(prev => [...prev, { type: 'user', text: input }]);

    const onAddHistory = (item: LogItem) => setHistory(prev => [...prev, item]);
    const onResetHistory = () => {
      setHistory([]);
      setIsExecuting(false);
      setThinking(initialThinkingState);
    };
    const onThinking = (state: Partial<ThinkingState>) => {
      setThinking(prev => ({ ...prev, ...state }));
    };

    await engineExecuteCommand(input, onAddHistory, onResetHistory, onThinking);

    if (input.trim() !== '/clear' && input.trim() !== '/settings') {
      setIsExecuting(false);
      setThinking(initialThinkingState);
    }
  }, []);

  return { history, isExecuting, thinking, executeCommand };
}
