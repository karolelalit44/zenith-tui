import { Box, Text, useInput } from 'ink';
import React, { useCallback, useEffect, useState } from 'react';
import { useTheme } from '../../theme/ThemeContext';

interface MultiLineTextInputProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: (value: string) => void;
  placeholder?: string;
  focus?: boolean;
}

export const MultiLineTextInput: React.FC<MultiLineTextInputProps> = React.memo(
  ({ value, onChange, onSubmit, placeholder = '', focus = true }) => {
    const { theme } = useTheme();
    const [cursor, setCursor] = useState(value.length);

    useEffect(() => {
      if (cursor > value.length) setCursor(value.length);
    }, [value.length, cursor]);

    const handleInput = useCallback(
      (_input: string, key: any) => {
        if (!focus) return;

        // Pasted content is delivered as a multi-character chunk (_input.length > 1)
        if (_input.length > 1) {
          // Normalize line breaks: CRLF (\r\n) and CR (\r) -> LF (\n)
          // Convert tabs (\t) -> 2 spaces
          const cleanPaste = _input
            .replace(/\r\n/g, '\n')
            .replace(/\r/g, '\n')
            .replace(/\t/g, '  ');

          if (cleanPaste.length > 0) {
            const nextValue = value.slice(0, cursor) + cleanPaste + value.slice(cursor);
            onChange(nextValue);
            setCursor((c) => c + cleanPaste.length);
          }
          return;
        }

        // Single key press handling:
        // Submit on Enter key (key.return, '\n', or '\r')
        if (key.return || _input === '\n' || _input === '\r') {
          onSubmit(value);
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

        if (key.backspace || key.delete) {
          if (cursor > 0) {
            const nextValue = value.slice(0, cursor - 1) + value.slice(cursor);
            onChange(nextValue);
            setCursor((c) => c - 1);
          }
          return;
        }

        // Ignore meta/ctrl/escape keys except normal character inputs
        if (key.ctrl || key.meta || key.escape) return;

        if (_input.length > 0) {
          const cleanInput = _input.replace(/\r/g, '').replace(/\t/g, '  ');
          if (cleanInput.length > 0) {
            const nextValue = value.slice(0, cursor) + cleanInput + value.slice(cursor);
            onChange(nextValue);
            setCursor((c) => c + cleanInput.length);
          }
        }
      },
      [focus, value, cursor, onChange, onSubmit],
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
      const before = value.slice(0, cursor);
      const charAtCursor = value[cursor];
      const after = cursor < value.length ? value.slice(cursor + 1) : '';

      content = (
        <Text wrap="wrap">
          {before}
          {charAtCursor === '\n' ? (
            <>
              <Text inverse> </Text>
              {'\n'}
            </>
          ) : (
            <Text inverse>{charAtCursor || ' '}</Text>
          )}
          {after}
        </Text>
      );
    }

    return (
      <Box width="100%">
        {content}
      </Box>
    );
  },
);

MultiLineTextInput.displayName = 'MultiLineTextInput';
