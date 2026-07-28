import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import { useCallback, useRef, useState } from 'react';
const MAX_HISTORY = 50;
const HISTORY_DIR = path.join(os.homedir(), '.zenith');
const HISTORY_PATH = path.join(HISTORY_DIR, 'history.json');
function loadHistoryFromDisk() {
    try {
        if (fs.existsSync(HISTORY_PATH)) {
            const raw = fs.readFileSync(HISTORY_PATH, 'utf-8');
            const parsed = JSON.parse(raw);
            if (Array.isArray(parsed)) {
                return parsed.slice(-MAX_HISTORY);
            }
        }
    }
    catch {
        // Ignore read errors
    }
    return [];
}
function saveHistoryToDisk(history) {
    try {
        if (!fs.existsSync(HISTORY_DIR)) {
            fs.mkdirSync(HISTORY_DIR, { recursive: true });
        }
        fs.writeFileSync(HISTORY_PATH, JSON.stringify(history.slice(-MAX_HISTORY), null, 2), 'utf-8');
    }
    catch {
        // Ignore write errors
    }
}
export function useAutocomplete() {
    const [input, setInput] = useState('');
    const [showAutocomplete, setShowAutocomplete] = useState(false);
    const [showFilePicker, setShowFilePicker] = useState(false);
    const [attachments, setAttachments] = useState([]);
    const historyRef = useRef(loadHistoryFromDisk());
    const historyIndexRef = useRef(-1);
    const handleInputChange = useCallback((val) => {
        setInput(val);
        historyIndexRef.current = -1;
        if (val.startsWith('/')) {
            setShowAutocomplete(true);
            setShowFilePicker(false);
        }
        else if (val.startsWith('@')) {
            setShowFilePicker(true);
            setShowAutocomplete(false);
        }
        else {
            setShowAutocomplete(false);
            setShowFilePicker(false);
        }
    }, []);
    const handleAutocompleteSelect = useCallback((cmd) => {
        setInput(cmd);
        setShowAutocomplete(false);
    }, []);
    const clearInput = useCallback(() => {
        setInput('');
        setShowAutocomplete(false);
        setShowFilePicker(false);
        historyIndexRef.current = -1;
    }, []);
    const addHistory = useCallback((prompt) => {
        if (!prompt.trim() || prompt.startsWith('/'))
            return;
        const hist = historyRef.current;
        if (hist.length > 0 && hist[hist.length - 1] === prompt)
            return;
        hist.push(prompt);
        if (hist.length > MAX_HISTORY) {
            hist.splice(0, hist.length - MAX_HISTORY);
        }
        historyIndexRef.current = -1;
        saveHistoryToDisk(hist);
    }, []);
    const historyUp = useCallback(() => {
        const hist = historyRef.current;
        if (hist.length === 0)
            return undefined;
        const newIdx = historyIndexRef.current + 1;
        if (newIdx >= hist.length)
            return undefined;
        historyIndexRef.current = newIdx;
        return hist[hist.length - 1 - newIdx];
    }, []);
    const historyDown = useCallback(() => {
        const hist = historyRef.current;
        if (historyIndexRef.current <= 0) {
            historyIndexRef.current = -1;
            return '';
        }
        historyIndexRef.current -= 1;
        return hist[hist.length - 1 - historyIndexRef.current];
    }, []);
    const insertFilePath = useCallback((relPath) => {
        setInput((prev) => {
            const cleaned = prev.replace(/^@/, '');
            return cleaned ? `${cleaned} ${relPath}` : relPath;
        });
        setShowFilePicker(false);
    }, []);
    const closeFilePicker = useCallback(() => {
        setShowFilePicker(false);
    }, []);
    const closeAutocomplete = useCallback(() => {
        setShowAutocomplete(false);
    }, []);
    const addAttachment = useCallback((attachment) => {
        setAttachments((prev) => [...prev, attachment]);
    }, []);
    const removeAttachment = useCallback((index) => {
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
        closeAutocomplete,
        addHistory,
        historyUp,
        historyDown,
        attachments,
        addAttachment,
        removeAttachment,
        clearAttachments,
    };
}
