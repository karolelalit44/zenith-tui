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
  const [history] = useState<string[]>([]);

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
  }, []);

  const addHistory = useCallback((prompt: string) => {
    if (!prompt.trim() || prompt.startsWith('/')) return;
    // History is stored but not navigable via arrows (Enter = newline, not submit)
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
