import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import { useCallback, useRef, useState } from 'react';
import type { FileAttachment } from '../types/scenario';
import { activeMentionAtOffset, insertMentionAt, replaceMention } from '../utils/mentionTokens';

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
  /** The current folder being browsed in the picker ('' = workspace root). */
  pickerPath: string;
  /** The initial filter seed for the picker (mid-text @ prefix). */
  pickerQuery: string;
  handleInputChange: (val: string, cursor?: number) => void;
  handleAutocompleteSelect: (cmd: string) => void;
  clearInput: () => void;
  insertFilePath: (relPath: string, kind?: 'file' | 'folder') => void;
  closeFilePicker: () => void;
  closeAutocomplete: () => void;
  addHistory: (prompt: string) => void;
  historyUp: () => string | undefined;
  historyDown: () => string | undefined;
  attachments: FileAttachment[];
  removeAttachment: (index: number) => void;
  clearAttachments: () => void;
}

export function useAutocomplete(): UseAutocompleteReturn {
  const [input, setInput] = useState('');
  const [cursor, setCursor] = useState(0);
  const [showAutocomplete, setShowAutocomplete] = useState(false);
  const [showFilePicker, setShowFilePicker] = useState(false);
  const [pickerPath, setPickerPath] = useState('');
  const [pickerQuery, setPickerQuery] = useState('');
  const [attachments, setAttachments] = useState<FileAttachment[]>([]);
  const historyRef = useRef<string[]>(loadHistoryFromDisk());
  const historyIndexRef = useRef(-1);
  const draftRef = useRef('');
  const cursorRef = useRef(0);
  cursorRef.current = cursor;

  const handleInputChange = useCallback((val: string, newCursor?: number) => {
    const cur = typeof newCursor === 'number' ? newCursor : val.length;
    setInput(val);
    setCursor(cur);
    cursorRef.current = cur;
    historyIndexRef.current = -1;
    const mention = activeMentionAtOffset(val, cur);
    if (mention) {
      setShowFilePicker(true);
      setShowAutocomplete(false);
      setPickerQuery(mention.text);
      setPickerPath('');
    } else if (SLASH_PATTERN.test(val)) {
      setShowAutocomplete(true);
      setShowFilePicker(false);
      setPickerQuery('');
    } else {
      setShowAutocomplete(false);
      setShowFilePicker(false);
      setPickerQuery('');
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
    setCursor(0);
    cursorRef.current = 0;
    setShowAutocomplete(false);
    setShowFilePicker(false);
    setPickerQuery('');
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
    (relPath: string, kind: 'file' | 'folder' = 'file') => {
      // Replace the active @mention token at the cursor with the inline @path,
      // preserving all other surrounding text. If there is no active token (edge
      // case), insert the mention at the cursor.
      const cur = cursorRef.current;
      const mention = activeMentionAtOffset(input, cur);
      let size = 0;
      try {
        const stat = fs.statSync(path.resolve(relPath));
        size = kind === 'folder' ? stat.size : stat.size;
      } catch {
        /* size unknown */
      }
      if (mention) {
        const { value, end } = replaceMention(input, mention, relPath);
        setInput(value);
        setCursor(end);
        cursorRef.current = end;
      } else {
        const { value, end } = insertMentionAt(input, cur, relPath);
        setInput(value);
        setCursor(end);
        cursorRef.current = end;
      }
      addAttachment({
        path: relPath,
        name: path.basename(relPath),
        mimeType: kind === 'folder' ? 'inode/directory' : mimeTypeForPath(relPath),
        size,
        kind,
      });
      setShowFilePicker(false);
      setPickerPath('');
      setPickerQuery('');
    },
    [addAttachment, input],
  );

  const closeFilePicker = useCallback(() => {
    setShowFilePicker(false);
    setPickerPath('');
    setPickerQuery('');
  }, []);

  const closeAutocomplete = useCallback(() => {
    setShowAutocomplete(false);
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
    pickerPath,
    pickerQuery,
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
    clearAttachments,
  };
}
