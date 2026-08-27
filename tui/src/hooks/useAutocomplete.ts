import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import { useCallback, useRef, useState } from 'react';
import type { FileAttachment } from '../types/scenario';

const MAX_HISTORY = 200;
const HISTORY_DIR = path.join(os.homedir(), '.zenith');
const HISTORY_PATH = path.join(HISTORY_DIR, 'history.json');

const SLASH_PATTERN = /^\/[^\s]*$/;

const MIME_TYPES: Record<string, string> = {
  '.md': 'text/markdown',
  '.txt': 'text/plain',
  '.json': 'application/json',
  '.jsonc': 'application/json',
  '.js': 'text/javascript',
  '.jsx': 'text/jsx',
  '.ts': 'text/typescript',
  '.tsx': 'text/typescript',
  '.py': 'text/x-python',
  '.toml': 'text/x-toml',
  '.yaml': 'text/yaml',
  '.yml': 'text/yaml',
  '.html': 'text/html',
  '.css': 'text/css',
  '.sh': 'application/x-sh',
  '.rs': 'text/rust',
  '.go': 'text/x-go',
  '.c': 'text/x-c',
  '.h': 'text/x-c',
  '.cpp': 'text/x-c++',
  '.csv': 'text/csv',
};

function mimeTypeForPath(relPath: string): string {
  return MIME_TYPES[path.extname(relPath).toLowerCase()] ?? 'text/plain';
}

function loadHistoryFromDisk(): string[] {
  try {
    if (fs.existsSync(HISTORY_PATH)) {
      const raw = fs.readFileSync(HISTORY_PATH, 'utf-8');
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) {
        return parsed.slice(-MAX_HISTORY);
      }
    }
  } catch (err) {
    console.warn('Failed to load command history:', err);
  }
  return [];
}

function saveHistoryToDisk(history: string[]): void {
  try {
    if (!fs.existsSync(HISTORY_DIR)) {
      fs.mkdirSync(HISTORY_DIR, { recursive: true });
    }
    fs.writeFileSync(HISTORY_PATH, JSON.stringify(history.slice(-MAX_HISTORY), null, 2), 'utf-8');
  } catch (err) {
    console.warn('Failed to save command history:', err);
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
  closeAutocomplete: () => void;
  addHistory: (prompt: string) => void;
  historyUp: () => string | undefined;
  historyDown: () => string | undefined;
  attachments: FileAttachment[];
  removeAttachment: (index: number) => void;
}

export function useAutocomplete(): UseAutocompleteReturn {
  const [input, setInput] = useState('');
  const [showAutocomplete, setShowAutocomplete] = useState(false);
  const [showFilePicker, setShowFilePicker] = useState(false);
  const [attachments, setAttachments] = useState<FileAttachment[]>([]);
  const historyRef = useRef<string[]>(loadHistoryFromDisk());
  const historyIndexRef = useRef(-1);
  const draftRef = useRef('');

  const handleInputChange = useCallback((val: string) => {
    setInput(val);
    historyIndexRef.current = -1;
    if (val.startsWith('@')) {
      setShowFilePicker(true);
      setShowAutocomplete(false);
    } else if (SLASH_PATTERN.test(val)) {
      setShowAutocomplete(true);
      setShowFilePicker(false);
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
    setInput((prev) => {
      if (prev === '' && draftRef.current) {
        const draft = draftRef.current;
        draftRef.current = '';
        return draft;
      }
      return '';
    });
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
    draftRef.current = prompt;
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
      return undefined;
    }
    historyIndexRef.current -= 1;
    return hist[hist.length - 1 - historyIndexRef.current];
  }, []);

  const addAttachment = useCallback((attachment: FileAttachment) => {
    setAttachments((prev) => [...prev, attachment]);
  }, []);

  const insertFilePath = useCallback(
    (relPath: string) => {
      setInput((prev) => prev.replace(/^@/, ''));
      let size = 0;
      try {
        size = fs.statSync(path.resolve(relPath)).size;
      } catch {}
      addAttachment({
        path: relPath,
        name: path.basename(relPath),
        mimeType: mimeTypeForPath(relPath),
        size,
      });
      setShowFilePicker(false);
    },
    [addAttachment],
  );

  const closeFilePicker = useCallback(() => {
    setShowFilePicker(false);
  }, []);

  const closeAutocomplete = useCallback(() => {
    setShowAutocomplete(false);
  }, []);

  const removeAttachment = useCallback((index: number) => {
    setAttachments((prev) => prev.filter((_, i) => i !== index));
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
    closeAutocomplete,
    addHistory,
    historyUp,
    historyDown,
    attachments,
    removeAttachment,
  };
}
