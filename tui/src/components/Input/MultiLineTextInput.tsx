import { Box, type Key, Text, useInput } from 'ink';
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { matchKeypress } from '../../config/keybind';
import { useTheme } from '../../theme/ThemeContext';

const MIN_LINES = 1;
const HARD_MAX_LINES = 15;

function computeMaxLines(): number {
  return Math.max(MIN_LINES, Math.min(HARD_MAX_LINES, Math.floor((process.stdout.rows ?? 24) / 3)));
}

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
      if (cursor > value.length) setCursor(value.length);
    }, [value.length, cursor]);

    useEffect(() => {
      setHistoryIndex(-1);
    }, []);

    const lines = useMemo(() => value.split('\n'), [value]);
    const maxLines = useMemo(computeMaxLines, []);
    const lineCount = Math.max(MIN_LINES, Math.min(maxLines, lines.length));

    const handleInput = useCallback(
      (_input: string, key: Key) => {
        if (!focus) return;

        if (onSpecial?.(_input, key, value)) {
          return;
        }

        if (_input.length > 1) {
          let cleanPaste = _input
            .replace(/\r\n/g, '\n')
            .replace(/\r/g, '\n')
            .replace(/\t/g, '  ')

            .replace(/\x1b\[[0-9;]*[a-zA-Z]/g, '')

            .replace(/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/g, '');

          if (cleanPaste.includes('\\"') || cleanPaste.includes('\\n')) {
            try {
              cleanPaste = JSON.parse(`"${cleanPaste.replace(/"/g, '\\"')}"`);
            } catch {}
          }
          if (cleanPaste.length > 0) {
            const nextValue = value.slice(0, cursor) + cleanPaste + value.slice(cursor);
            onChange(nextValue);
            setCursor((c) => c + cleanPaste.length);
          }
          return;
        }

        const pressed = matchKeypress(_input, key);
        const isEnter = key.return || _input === '\n' || _input === '\r';
        const newlineModifier = key.shift || key.ctrl || key.meta;

        if (pressed.includes('submit') || (isEnter && !newlineModifier)) {
          onSubmit(value);
          return;
        }

        if (pressed.includes('newline') || (isEnter && newlineModifier)) {
          const nextValue = `${value.slice(0, cursor)}\n${value.slice(cursor)}`;
          onChange(nextValue);
          setCursor((c) => c + 1);
          return;
        }

        if (pressed.includes('history_up')) {
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

        if (pressed.includes('history_down')) {
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
      [focus, value, cursor, onChange, onSubmit, lines, historyUp, historyDown, onSpecial],
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

      content = lines.map((line, lineIdx) => {
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
      });
    }

    return (
      <Box width="100%" height={lineCount}>
        {content}
      </Box>
    );
  },
);

MultiLineTextInput.displayName = 'MultiLineTextInput';
