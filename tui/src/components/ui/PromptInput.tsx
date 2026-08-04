import { Box, Text, useInput } from 'ink';
import React, { useCallback } from 'react';
import { useTheme } from '../../theme/ThemeContext';
import { useTextBuffer } from './textBuffer';

interface PromptInputProps {
  title: string;
  description?: React.ReactNode;
  placeholder?: string;
  value?: string;
  masked?: boolean;
  busy?: boolean;
  busyText?: string;
  footer?: React.ReactNode;
  submitLabel?: string;
  onSubmit: (value: string) => void;
  onCancel: () => void;
}

export const PromptInput: React.FC<PromptInputProps> = ({
  title,
  description,
  placeholder = 'Enter text',
  value = '',
  masked = false,
  busy = false,
  busyText = 'Working...',
  footer,
  submitLabel = 'submit',
  onSubmit,
  onCancel,
}) => {
  const { theme } = useTheme();
  const buffer = useTextBuffer(value);

  const confirm = useCallback(() => {
    if (busy) return;
    onSubmit(buffer.value);
  }, [busy, buffer.value, onSubmit]);

  useInput((char, key) => {
    if (key.escape) {
      onCancel();
      return;
    }
    if (key.return) {
      confirm();
      return;
    }
    buffer.handleKey(char, key);
  });

  const displayValue = masked ? '•'.repeat(buffer.value.length) : buffer.value;

  return (
    <Box flexDirection="column" width="100%">
      <Box flexDirection="row" justifyContent="space-between" paddingLeft={2} paddingRight={2}>
        <Text color={theme.colors.text.ethereal} bold>
          {title}
        </Text>
        <Text color={theme.colors.text.muted}>esc</Text>
      </Box>
      <Box flexDirection="column" paddingLeft={2} paddingRight={2} marginTop={1} gap={1}>
        {description}
        <Box flexDirection="row">
          <Text color={theme.colors.text.muted}>▸ </Text>
          <Text color={busy ? theme.colors.text.dim : theme.colors.text.ethereal}>
            {displayValue.slice(0, buffer.cursor)}
            <Text color={theme.colors.status.accent} inverse>
              {displayValue[buffer.cursor] ?? ' '}
            </Text>
            {displayValue.slice(buffer.cursor + 1)}
            {displayValue.length === 0 && !busy && <Text color={theme.colors.text.dim}>{placeholder}</Text>}
          </Text>
        </Box>
      </Box>
      <Box
        flexDirection="row"
        justifyContent="space-between"
        marginTop={1}
        paddingLeft={2}
        paddingRight={2}
        paddingBottom={1}
      >
        {footer ? <Text color={theme.colors.text.muted}>{footer}</Text> : null}
        <Text color={theme.colors.text.muted}>
          {busy ? (
            <Text italic>{busyText}</Text>
          ) : (
            <>
              <Text color={theme.colors.status.success}>⏎</Text> {submitLabel}
            </>
          )}
        </Text>
      </Box>
    </Box>
  );
};
