import { Box, type Key, Text, useInput } from 'ink';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { matchKeypress } from '../../config/keybind';
import { useTheme } from '../../theme/ThemeContext';
import { expandPastedMarkers, insertOrMergePaste } from '../../utils/pasteTracker';

interface MultiLineTextInputProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: (value: string) => void;
  placeholder?: string;
  focus?: boolean;
  historyUp?: () => string | undefined;
  historyDown?: () => string | undefined;

  onSpecial?: (char: string, key: Key, value: string) => boolean;
}

export const MultiLineTextInput: React.FC<MultiLineTextInputProps> = React.memo(
  ({ value, onChange, onSubmit, placeholder = '', focus = true, historyUp, historyDown, onSpecial }) => {
    const { theme } = useTheme();
    const [cursor, setCursor] = useState(value.length);
    const [_historyIndex, setHistoryIndex] = useState(-1);

    useEffect(() => {
      if (cursor > value.length) {
        cursorRef.current = value.length;
        setCursor(value.length);
      }
    }, [value.length, cursor]);

    useEffect(() => {
      setHistoryIndex(-1);
    }, []);

    const lines = useMemo(() => value.split('\n'), [value]);

    // Refs mirror the latest committed render so the useInput handler never reads
    // a stale closure when keypresses arrive between renders (e.g. a paste right
    // after a slash command clears the input). Every mutation below also updates
    // valueRef/cursorRef synchronously BEFORE state commits: winpty and terminal
    // emulators can deliver one large paste as multiple stdin chunks within the
    // same tick, and relying on the render to sync the refs would make each chunk
    // overwrite the previous one instead of appending.
    const valueRef = useRef(value);
    valueRef.current = value;
    const cursorRef = useRef(cursor);
    cursorRef.current = cursor;
    const linesRef = useRef(lines);
    linesRef.current = lines;

    const handleInput = useCallback(
      (_input: string, key: Key) => {
        if (!focus) return;
        const currentValue = valueRef.current;
        const currentCursor = cursorRef.current;
        const currentLines = linesRef.current;

        if (onSpecial?.(_input, key, currentValue)) {
          return;
        }

        if (_input.length > 1) {
          const cleanPaste = _input
            .replace(/\r\n/g, '\n')
            .replace(/\r/g, '\n')
            .replace(/\t/g, '  ')
            .replace(/\x1b\[[0-9;]*[a-zA-Z]/g, '')
            .replace(/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/g, '');

          if (cleanPaste.length > 0) {
            const { nextValue, nextCursor } = insertOrMergePaste(currentValue, currentCursor, cleanPaste);
            valueRef.current = nextValue;
            cursorRef.current = nextCursor;
            onChange(nextValue);
            setCursor(nextCursor);
          }
          return;
        }

        const pressed = matchKeypress(_input, key);
        const isEnter = key.return || _input === '\n' || _input === '\r';
        const newlineModifier = key.shift || key.ctrl || key.meta;

        if (pressed.includes('submit') || (isEnter && !newlineModifier)) {
          const expandedValue = expandPastedMarkers(currentValue);
          onSubmit(expandedValue);
          return;
        }

        if (pressed.includes('newline') || (isEnter && newlineModifier)) {
          const nextValue = `${currentValue.slice(0, currentCursor)}\n${currentValue.slice(currentCursor)}`;
          valueRef.current = nextValue;
          cursorRef.current = currentCursor + 1;
          onChange(nextValue);
          setCursor(cursorRef.current);
          return;
        }

        if (pressed.includes('history_up')) {
          const currentLineIdx = currentValue.slice(0, currentCursor).split('\n').length - 1;
          if (currentLineIdx === 0 && historyUp) {
            const prev = historyUp();
            if (prev !== undefined) {
              valueRef.current = prev;
              cursorRef.current = prev.length;
              onChange(prev);
              setCursor(prev.length);
            }
            return;
          }
          const prevNewline = currentValue.lastIndexOf('\n', currentCursor - 1);
          if (prevNewline >= 0) {
            cursorRef.current = prevNewline;
            setCursor(prevNewline);
          }
          return;
        }

        if (pressed.includes('history_down')) {
          const currentLineIdx = currentValue.slice(0, currentCursor).split('\n').length - 1;
          if (currentLineIdx >= currentLines.length - 1 && historyDown) {
            const next = historyDown();
            if (next !== undefined) {
              valueRef.current = next;
              cursorRef.current = next.length;
              onChange(next);
              setCursor(next.length);
            }
            return;
          }
          const nextNewline = currentValue.indexOf('\n', currentCursor);
          if (nextNewline >= 0 && nextNewline < currentValue.length) {
            cursorRef.current = nextNewline + 1;
            setCursor(nextNewline + 1);
          }
          return;
        }

        if (key.leftArrow) {
          if (currentCursor > 0) {
            cursorRef.current = currentCursor - 1;
            setCursor(cursorRef.current);
          }
          return;
        }

        if (key.rightArrow) {
          if (currentCursor < currentValue.length) {
            cursorRef.current = currentCursor + 1;
            setCursor(cursorRef.current);
          }
          return;
        }

        if (key.home) {
          const lastNewline = currentValue.lastIndexOf('\n', currentCursor - 1);
          cursorRef.current = lastNewline + 1;
          setCursor(cursorRef.current);
          return;
        }

        if (key.end) {
          const nextNewline = currentValue.indexOf('\n', currentCursor);
          cursorRef.current = nextNewline >= 0 ? nextNewline : currentValue.length;
          setCursor(cursorRef.current);
          return;
        }

        if (key.backspace || key.delete) {
          if (currentCursor > 0) {
            const nextValue = currentValue.slice(0, currentCursor - 1) + currentValue.slice(currentCursor);
            valueRef.current = nextValue;
            cursorRef.current = currentCursor - 1;
            onChange(nextValue);
            setCursor(cursorRef.current);
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
            const nextValue = currentValue.slice(0, currentCursor) + cleanInput + currentValue.slice(currentCursor);
            valueRef.current = nextValue;
            cursorRef.current = currentCursor + cleanInput.length;
            onChange(nextValue);
            setCursor(cursorRef.current);
          }
        }
      },
      [focus, onChange, onSubmit, historyUp, historyDown, onSpecial],
    );

    useInput(handleInput, { isActive: focus });

    let content: React.ReactNode;
    if (value.length === 0) {
      content = (
        <Text wrap="wrap">
          <Text inverse color={theme.colors.text.bright}>
            {' '}
          </Text>
          <Text color={theme.colors.text.dim}>{placeholder}</Text>
        </Text>
      );
    } else {
      const cursorLineIdx = value.slice(0, cursor).split('\n').length - 1;
      const cursorCol = cursor - (value.lastIndexOf('\n', cursor - 1) + 1);

      const renderStyledSegment = (text: string) => {
        const parts = text.split(/(\[Pasted (?:(?:\+\d+ lines)|\d+ chars) #\d+\])/g);
        return parts.map((part, i) => {
          const match = part.match(/\[Pasted ((?:\+\d+ lines)|\d+ chars) #\d+\]/);
          if (match) {
            return (
              <Text key={i} color={theme.colors.status.info} bold>
                [{`Pasted ${match[1]}`}]
              </Text>
            );
          }
          return <Text key={i}>{part}</Text>;
        });
      };

      content = lines.map((line, lineIdx) => {
        const isCursorLine = lineIdx === cursorLineIdx;
        if (isCursorLine) {
          const before = renderStyledSegment(line.slice(0, cursorCol));
          const charAtCursor = line[cursorCol];
          const after = renderStyledSegment(line.slice(cursorCol + 1));
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
            {renderStyledSegment(line)}
          </Text>
        );
      });
    }

    return (
      <Box flexDirection="column" width="100%">
        {content}
      </Box>
    );
  },
);

MultiLineTextInput.displayName = 'MultiLineTextInput';
