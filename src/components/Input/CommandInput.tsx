import { Box, Text } from 'ink';
import TextInput from 'ink-text-input';
import React from 'react';
import { useTheme } from '../../theme/ThemeContext';

export interface CommandInputProps {
  input: string;
  selectedMode: string;
  onInputChange: (value: string) => void;
  onSubmit: (value: string) => void;
}

export const CommandInput: React.FC<CommandInputProps> = React.memo(
  ({ input, selectedMode, onInputChange, onSubmit }) => {
    const { theme } = useTheme();

    return (
      <Box
        flexDirection="column"
        width="100%"
        borderStyle="round"
        borderColor={theme.colors.border.active}
        paddingX={1}
        paddingY={0}
        marginTop={1}
      >
        {/* Primary Input Line */}
        <Box flexDirection="row" alignItems="center">
          <Text color={theme.colors.text.emerald} bold>
            ❯{' '}
          </Text>
          <TextInput
            value={input}
            onChange={onInputChange}
            onSubmit={onSubmit}
            placeholder="Ask anything or type / for commands..."
            focus={true}
          />
        </Box>

        {/* Subtle Divider & Hints Bar */}
        <Box
          flexDirection="row"
          justifyContent="space-between"
          alignItems="center"
          marginTop={0}
          paddingTop={0}
          borderStyle="single"
          borderTop={true}
          borderBottom={false}
          borderLeft={false}
          borderRight={false}
          borderColor={theme.colors.border.muted}
        >
          <Box flexDirection="row" alignItems="center">
            <Text color={theme.colors.status.accent} bold>
              [{selectedMode.toUpperCase()}]
            </Text>
          </Box>

          <Box flexDirection="row" alignItems="center">
            <Text color={theme.colors.text.muted} bold>
              Shift+Enter
            </Text>
            <Text color={theme.colors.text.dim}> newline </Text>
            <Text color={theme.colors.text.muted} bold>
              /
            </Text>
            <Text color={theme.colors.text.dim}> commands </Text>
            <Text color={theme.colors.text.muted} bold>
              @
            </Text>
            <Text color={theme.colors.text.dim}> files</Text>
          </Box>
        </Box>
      </Box>
    );
  },
);
