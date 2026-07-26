import { Box, Text, useInput, type Key } from 'ink';
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useTheme } from '../../theme/ThemeContext';

const MIN_LINES = 1;
const MAX_LINES = 15;

interface MultiLineTextInputProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: (value: string) => void;
  placeholder?: string;
  focus?: boolean;
  historyUp?: () => string | undefined;
  historyDown?: () => string | undefined;
}

export const MultiLineTextInput: React.FC<MultiLineTextInputProps> = React.memo(
  ({ value, onChange, onSubmit, placeholder = '', focus = true, historyUp, historyDown }) => {
    const { theme } = useTheme();
    const [cursor, setCursor] = useState(value.length);
    const [historyIndex, setHistoryIndex] = useState(-1);

    useEffect(() => {
      if (cursor > value.length) setCursor(value.length);
    }, [value.length, cursor]);

    useEffect(() => {
      setHistoryIndex(-1);
    }, [value]);

    const lines = useMemo(() => value.split('\n'), [value]);
    const lineCount = Math.max(MIN_LINES, Math.min(MAX_LINES, lines.length));

    const handleInput = useCallback(
      (_input: string, key: Key) => {
        if (!focus) return;

        if (_input.length > 1) {
          let cleanPaste = _input
            .replace(/\r\n/g, '\n')
            .replace(/\r/g, '\n')
            .replace(/\t/g, '  ')
            // Strip ANSI escape sequences
            .replace(/\x1b\[[0-9;]*[a-zA-Z]/g, '')
            // Strip control chars (keep \n only)
            .replace(/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/g, '');
          // Unescape JSON-encoded strings (e.g. \"key\": \"value\")
          if (cleanPaste.includes('\\"') || cleanPaste.includes('\\n')) {
            try {
              cleanPaste = JSON.parse(`"${cleanPaste.replace(/"/g, '\\"')}"`);
            } catch {
              // Not valid JSON escape — use as-is
            }
          }
          if (cleanPaste.length > 0) {
            const nextValue = value.slice(0, cursor) + cleanPaste + value.slice(cursor);
            onChange(nextValue);
            setCursor((c) => c + cleanPaste.length);
          }
          return;
        }

        if (key.return || _input === '\n' || _input === '\r') {
          if (key.shift || key.ctrl) {
            const nextValue = value.slice(0, cursor) + '\n' + value.slice(cursor);
            onChange(nextValue);
            setCursor((c) => c + 1);
          } else {
            onSubmit(value);
          }
          return;
        }

        if (key.upArrow) {
          const currentLineIdx = value.slice(0, cursor).split('\n').length - 1;
          if (currentLineIdx === 0 && historyUp) {
            const prev = historyUp();
            if (prev !== undefined) {
              onChange(prev);
              setCursor(prev.length);
            }
            return;
          }
          const prevNewline = value.lastIndexOf('\n', cursor - 1);
          if (prevNewline >= 0) {
            setCursor(prevNewline);
          }
          return;
        }

        if (key.downArrow) {
          const currentLineIdx = value.slice(0, cursor).split('\n').length - 1;
          if (currentLineIdx >= lines.length - 1 && historyDown) {
            const next = historyDown();
            if (next !== undefined) {
              onChange(next);
              setCursor(next.length);
            }
            return;
          }
          const nextNewline = value.indexOf('\n', cursor);
          if (nextNewline >= 0 && nextNewline < value.length) {
            setCursor(nextNewline + 1);
          }
          return;
        }

        if (key.leftArrow) {
          if (cursor > 0) setCursor((c) => c - 1);
          return;
        }

        if (key.rightArrow) {
          if (cursor < value.length) setCursor((c) => c + 1);
          return;
        }

        if (key.home) {
          const lastNewline = value.lastIndexOf('\n', cursor - 1);
          setCursor(lastNewline + 1);
          return;
        }

        if (key.end) {
          const nextNewline = value.indexOf('\n', cursor);
          setCursor(nextNewline >= 0 ? nextNewline : value.length);
          return;
        }

        if (key.backspace || key.delete) {
          if (cursor > 0) {
            const nextValue = value.slice(0, cursor - 1) + value.slice(cursor);
            onChange(nextValue);
            setCursor((c) => c - 1);
          }
          return;
        }

        if ((key.ctrl || key.meta) && (_input === 'o' || _input === 'O')) {
          return;
        }

        if (key.ctrl || key.meta || key.escape) return;

        if (_input.length > 0) {
          const cleanInput = _input
            .replace(/\r/g, '')
            .replace(/\t/g, '  ')
            .replace(/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/g, '');
          if (cleanInput.length > 0) {
            const nextValue = value.slice(0, cursor) + cleanInput + value.slice(cursor);
            onChange(nextValue);
            setCursor((c) => c + cleanInput.length);
          }
        }
      },
      [focus, value, cursor, onChange, onSubmit, lines, historyUp, historyDown],
    );

    useInput(handleInput, { isActive: focus });

    let content: React.ReactNode;
    if (value.length === 0) {
      content = (
        <Text>
          <Text inverse color={theme.colors.text.bright}>
            {placeholder ? placeholder[0] : ' '}
          </Text>
          <Text color={theme.colors.text.dim}>{placeholder ? placeholder.slice(1) : ''}</Text>
        </Text>
      );
    } else {
      const cursorLineIdx = value.slice(0, cursor).split('\n').length - 1;
      const cursorCol = cursor - (value.lastIndexOf('\n', cursor - 1) + 1);

      content = (
        <>
          {lines.map((line, lineIdx) => {
            const isCursorLine = lineIdx === cursorLineIdx;
            if (isCursorLine) {
              const before = line.slice(0, cursorCol);
              const charAtCursor = line[cursorCol];
              const after = line.slice(cursorCol + 1);
              return (
                <Text key={lineIdx} wrap="wrap">
                  {before}
                  <Text inverse>{charAtCursor || ' '}</Text>
                  {after}
                </Text>
              );
            }
            return (
              <Text key={lineIdx} wrap="wrap">
                {line || ' '}
              </Text>
            );
          })}
        </>
      );
    }

    return (
      <Box width="100%" height={lineCount}>
        {content}
      </Box>
    );
  },
);

MultiLineTextInput.displayName = 'MultiLineTextInput';
