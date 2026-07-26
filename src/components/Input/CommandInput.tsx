import { Box, Text } from 'ink';
import React from 'react';
import { useTheme } from '../../theme/ThemeContext';
import type { FileAttachment } from '../../types/scenario';
import { MultiLineTextInput } from './MultiLineTextInput';

interface CommandInputProps {
  input: string;
  onInputChange: (value: string) => void;
  onSubmit: (value: string) => void;
  disabled?: boolean;
  attachments?: FileAttachment[];
  onRemoveAttachment?: (index: number) => void;
  historyUp?: () => string | undefined;
  historyDown?: () => string | undefined;
}

export const CommandInput: React.FC<CommandInputProps> = React.memo(
  ({ input, onInputChange, onSubmit, disabled = false, attachments, onRemoveAttachment, historyUp, historyDown }) => {
    const { theme } = useTheme();

    return (
      <Box
        flexDirection="column"
        width="100%"
        borderStyle="round"
        borderColor={disabled ? theme.colors.border.muted : theme.colors.border.active}
        paddingX={1}
        paddingY={0}
        marginTop={1}
      >
        {attachments && attachments.length > 0 && (
          <Box flexDirection="row" flexWrap="wrap" marginBottom={0}>
            {attachments.map((att, idx) => (
              <Box key={idx} flexDirection="row" marginRight={1}>
                <Text color={theme.colors.status.info}>📎</Text>
                <Text color={theme.colors.text.ethereal}> {att.name}</Text>
                <Text color={theme.colors.text.muted}> </Text>
                <Text color={theme.colors.status.error}>(#{idx + 1})</Text>
              </Box>
            ))}
          </Box>
        )}
        <Box flexDirection="row" alignItems="flex-start">
          <Text color={disabled ? theme.colors.text.muted : theme.colors.text.emerald} bold>
            {disabled ? '◌' : '❯'}{' '}
          </Text>
          <Box flexDirection="column" flexGrow={1}>
            {disabled ? (
              <Box flexDirection="row" alignItems="center">
                <Text color={theme.colors.text.muted} italic>
                  Processing... (Esc to cancel)
                </Text>
              </Box>
            ) : (
              <MultiLineTextInput
                value={input}
                onChange={onInputChange}
                onSubmit={onSubmit}
                placeholder="Ask anything..."
                focus={!disabled}
                historyUp={historyUp}
                historyDown={historyDown}
              />
            )}
          </Box>
        </Box>
        <Box flexDirection="row" justifyContent="flex-end" marginTop={0}>
          {disabled ? (
            <Text color={theme.colors.text.muted}>
              Esc to cancel
            </Text>
          ) : input.trim() ? (
            <Text color={theme.colors.text.dim}>
              Enter ⏎ send
            </Text>
          ) : (
            <Text color={theme.colors.text.dim}>
              Enter ⏎ send · Shift+Enter ↵ newline · / commands
            </Text>
          )}
        </Box>
      </Box>
    );
  },
);
