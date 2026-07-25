import { Box, Text, useInput } from 'ink';
import chalk from 'chalk';
import React, { useCallback, useEffect, useState } from 'react';

interface MultiLineTextInputProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: (value: string) => void;
  placeholder?: string;
  focus?: boolean;
  maxVisibleLines?: number;
}

/**
 * Custom multi-line text input that handles long prompts and pasted content.
 * Replaces ink-text-input which renders everything as a single line.
 */
export const MultiLineTextInput: React.FC<MultiLineTextInputProps> = React.memo(
  ({
    value,
    onChange,
    onSubmit,
    placeholder = '',
    focus = true,
    maxVisibleLines = 12,
  }) => {
    const [cursorOffset, setCursorOffset] = useState(value.length);

    // Keep cursor at end when value changes externally
    useEffect(() => {
      if (cursorOffset > value.length) {
        setCursorOffset(value.length);
      }
    }, [value.length, cursorOffset]);

    // Split value into lines for display
    const lines = value.length > 0 ? value.split('\n') : [];
    const cursorLine = value.slice(0, cursorOffset).split('\n').length - 1;
    const cursorCol = cursorOffset - value.lastIndexOf('\n', cursorOffset - 1) - 1;

    // Calculate which lines are visible (scroll window)
    const totalLines = Math.max(lines.length, 1);
    const visibleEnd = totalLines;
    const visibleStart = Math.max(0, visibleEnd - maxVisibleLines);
    const visibleLines = lines.slice(visibleStart, visibleEnd);

    const handleInput = useCallback(
      (_input: string, key: any) => {
        if (!focus) return;

        if (key.return && !key.shift) {
          onSubmit(value);
          return;
        }

        if (key.upArrow) {
          if (cursorLine > 0) {
            const prevLineLen = lines[cursorLine - 1]?.length || 0;
            const newCol = Math.min(cursorCol, prevLineLen);
            let offset = 0;
            for (let i = 0; i < cursorLine - 1; i++) offset += (lines[i]?.length || 0) + 1;
            setCursorOffset(offset + newCol);
          }
          return;
        }

        if (key.downArrow) {
          if (cursorLine < lines.length - 1) {
            const nextLineLen = lines[cursorLine + 1]?.length || 0;
            const newCol = Math.min(cursorCol, nextLineLen);
            let offset = 0;
            for (let i = 0; i <= cursorLine; i++) offset += (lines[i]?.length || 0) + 1;
            setCursorOffset(offset + newCol);
          }
          return;
        }

        if (key.leftArrow) {
          if (cursorOffset > 0) setCursorOffset((c) => c - 1);
          return;
        }

        if (key.rightArrow) {
          if (cursorOffset < value.length) setCursorOffset((c) => c + 1);
          return;
        }

        if (key.backspace || key.delete) {
          if (cursorOffset > 0) {
            const next = value.slice(0, cursorOffset - 1) + value.slice(cursorOffset);
            setCursorOffset((c) => c - 1);
            onChange(next);
          }
          return;
        }

        // Skip special keys
        if (key.ctrl || key.meta || key.tab || key.escape) return;

        // Insert character(s) at cursor — handles paste (multi-char _input)
        if (_input.length > 0) {
          const next =
            value.slice(0, cursorOffset) + _input + value.slice(cursorOffset);
          setCursorOffset((c) => c + _input.length);
          onChange(next);
        }
      },
      [focus, value, cursorOffset, cursorLine, cursorCol, lines, onChange, onSubmit],
    );

    useInput(handleInput, { isActive: focus });

    // Build rendered lines with cursor
    const renderedLines: React.ReactNode[] = [];

    if (value.length === 0) {
      // Show placeholder with cursor
      renderedLines.push(
        <Text key="ph">
          {placeholder
            ? chalk.inverse(placeholder[0]) + chalk.grey(placeholder.slice(1))
            : chalk.inverse(' ')}
        </Text>,
      );
    } else {
      for (let i = 0; i < visibleLines.length; i++) {
        const lineIdx = visibleStart + i;
        const line = visibleLines[i];
        const isCursorLine = lineIdx === cursorLine;
        const isLastLine = lineIdx === lines.length - 1 && value.endsWith('\n') === false;

        if (!isCursorLine) {
          // Non-cursor lines render as plain text
          renderedLines.push(
            <Text key={`l${lineIdx}`}>
              {line || ' '}
            </Text>,
          );
        } else {
          // Cursor line: render with cursor highlight
          const before = line.slice(0, cursorCol);
          const atCursor = line[cursorCol] || ' ';
          const after = line.slice(cursorCol + 1);

          // If cursor is at end of line, show inverse space after
          const cursorElement =
            cursorCol >= line.length ? (
              <Text key={`c${lineIdx}`}>
                {before}
                {chalk.inverse(' ')}
              </Text>
            ) : (
              <Text key={`c${lineIdx}`}>
                {before}
                {chalk.inverse(atCursor)}
                {after}
              </Text>
            );

          renderedLines.push(cursorElement);

          // If this is the last line and cursor is at end, add trailing inverse space
          if (isLastLine && cursorCol >= line.length) {
            // Already handled above
          }
        }
      }
    }

    return (
      <Box flexDirection="column" width="100%">
        {renderedLines.map((node, idx) => (
          <Box key={idx} flexDirection="row" width="100%">
            {node}
          </Box>
        ))}
      </Box>
    );
  },
);

MultiLineTextInput.displayName = 'MultiLineTextInput';
