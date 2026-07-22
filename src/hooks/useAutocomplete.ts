import { useInput } from 'ink';
import { useCallback, useState } from 'react';

export interface UseAutocompleteReturn {
  input: string;
  showAutocomplete: boolean;
  showFilePicker: boolean;
  handleInputChange: (val: string) => void;
  handleAutocompleteSelect: (cmd: string) => void;
  clearInput: () => void;
  insertFilePath: (relPath: string) => void;
  closeFilePicker: () => void;
  addHistory: (prompt: string) => void;
}

export function useAutocomplete(): UseAutocompleteReturn {
  const [input, setInput] = useState('');
  const [showAutocomplete, setShowAutocomplete] = useState(false);
  const [showFilePicker, setShowFilePicker] = useState(false);
  const [history, setHistory] = useState<string[]>([]);
  const [historyIndex, setHistoryIndex] = useState(-1);

  const handleInputChange = useCallback((val: string) => {
    setInput(val);
    if (val.startsWith('/')) {
      setShowAutocomplete(true);
      setShowFilePicker(false);
    } else if (val.startsWith('@')) {
      setShowFilePicker(true);
      setShowAutocomplete(false);
    } else {
      setShowAutocomplete(false);
      setShowFilePicker(false);
    }
  }, []);

  const handleAutocompleteSelect = useCallback((cmd: string) => {
    setInput(cmd);
    setShowAutocomplete(false);
  }, []);

  const clearInput = useCallback(() => {
    setInput('');
    setShowAutocomplete(false);
    setShowFilePicker(false);
    setHistoryIndex(-1);
  }, []);

  const addHistory = useCallback((prompt: string) => {
    if (!prompt.trim() || prompt.startsWith('/')) return;
    setHistory((prev) => [prompt, ...prev.filter((p) => p !== prompt)]);
    setHistoryIndex(-1);
  }, []);

  const insertFilePath = useCallback((relPath: string) => {
    setInput((prev) => {
      const cleaned = prev.replace(/^@/, '');
      return cleaned ? `${cleaned} ${relPath}` : relPath;
    });
    setShowFilePicker(false);
  }, []);

  const closeFilePicker = useCallback(() => {
    setShowFilePicker(false);
  }, []);

  useInput((_char, key) => {
    if (showAutocomplete || showFilePicker) return;

    if (key.upArrow) {
      if (history.length === 0) return;
      const nextIdx = Math.min(history.length - 1, historyIndex + 1);
      setHistoryIndex(nextIdx);
      setInput(history[nextIdx]);
    } else if (key.downArrow) {
      if (historyIndex <= 0) {
        setHistoryIndex(-1);
        setInput('');
      } else {
        const nextIdx = historyIndex - 1;
        setHistoryIndex(nextIdx);
        setInput(history[nextIdx]);
      }
    }
  });

  return {
    input,
    showAutocomplete,
    showFilePicker,
    handleInputChange,
    handleAutocompleteSelect,
    clearInput,
    insertFilePath,
    closeFilePicker,
    addHistory,
  };
}
