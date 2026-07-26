import { useCallback, useRef, useState } from 'react';
import * as fs from 'fs';
import * as path from 'path';
import * as os from 'os';
import type { FileAttachment } from '../types/scenario';

const MAX_HISTORY = 50;
const HISTORY_DIR = path.join(os.homedir(), '.zenith');
const HISTORY_PATH = path.join(HISTORY_DIR, 'history.json');

function loadHistoryFromDisk(): string[] {
  try {
    if (fs.existsSync(HISTORY_PATH)) {
      const raw = fs.readFileSync(HISTORY_PATH, 'utf-8');
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) {
        return parsed.slice(-MAX_HISTORY);
      }
    }
  } catch {
    // Ignore read errors
  }
  return [];
}

function saveHistoryToDisk(history: string[]): void {
  try {
    if (!fs.existsSync(HISTORY_DIR)) {
      fs.mkdirSync(HISTORY_DIR, { recursive: true });
    }
    fs.writeFileSync(HISTORY_PATH, JSON.stringify(history.slice(-MAX_HISTORY), null, 2), 'utf-8');
  } catch {
    // Ignore write errors
  }
}

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
  historyUp: () => string | undefined;
  historyDown: () => string | undefined;
  attachments: FileAttachment[];
  addAttachment: (attachment: FileAttachment) => void;
  removeAttachment: (index: number) => void;
  clearAttachments: () => void;
}

export function useAutocomplete(): UseAutocompleteReturn {
  const [input, setInput] = useState('');
  const [showAutocomplete, setShowAutocomplete] = useState(false);
  const [showFilePicker, setShowFilePicker] = useState(false);
  const [attachments, setAttachments] = useState<FileAttachment[]>([]);
  const historyRef = useRef<string[]>(loadHistoryFromDisk());
  const historyIndexRef = useRef(-1);

  const handleInputChange = useCallback((val: string) => {
    setInput(val);
    historyIndexRef.current = -1;
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
    historyIndexRef.current = -1;
  }, []);

  const addHistory = useCallback((prompt: string) => {
    if (!prompt.trim() || prompt.startsWith('/')) return;
    const hist = historyRef.current;
    if (hist.length > 0 && hist[hist.length - 1] === prompt) return;
    hist.push(prompt);
    if (hist.length > MAX_HISTORY) {
      hist.splice(0, hist.length - MAX_HISTORY);
    }
    historyIndexRef.current = -1;
    saveHistoryToDisk(hist);
  }, []);

  const historyUp = useCallback((): string | undefined => {
    const hist = historyRef.current;
    if (hist.length === 0) return undefined;
    const newIdx = historyIndexRef.current + 1;
    if (newIdx >= hist.length) return undefined;
    historyIndexRef.current = newIdx;
    return hist[hist.length - 1 - newIdx];
  }, []);

  const historyDown = useCallback((): string | undefined => {
    const hist = historyRef.current;
    if (historyIndexRef.current <= 0) {
      historyIndexRef.current = -1;
      return '';
    }
    historyIndexRef.current -= 1;
    return hist[hist.length - 1 - historyIndexRef.current];
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

  const addAttachment = useCallback((attachment: FileAttachment) => {
    setAttachments((prev) => [...prev, attachment]);
  }, []);

  const removeAttachment = useCallback((index: number) => {
    setAttachments((prev) => prev.filter((_, i) => i !== index));
  }, []);

  const clearAttachments = useCallback(() => {
    setAttachments([]);
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
    historyUp,
    historyDown,
    attachments,
    addAttachment,
    removeAttachment,
    clearAttachments,
  };
}
