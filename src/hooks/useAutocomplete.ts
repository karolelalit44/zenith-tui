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
}

export function useAutocomplete(): UseAutocompleteReturn {
  const [input, setInput] = useState('');
  const [showAutocomplete, setShowAutocomplete] = useState(false);
  const [showFilePicker, setShowFilePicker] = useState(false);

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
  };
}
