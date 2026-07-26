import { Box, Text } from 'ink';
import React from 'react';
import { useTheme } from '../../theme/ThemeContext';
import { MultiLineTextInput } from './MultiLineTextInput';

interface CommandInputProps {
  input: string;
  onInputChange: (value: string) => void;
  onSubmit: (value: string) => void;
}

export const CommandInput: React.FC<CommandInputProps> = React.memo(
  ({ input, onInputChange, onSubmit }) => {
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
        <Box flexDirection="row" alignItems="flex-start">
          <Text color={theme.colors.text.emerald} bold>
            ❯{' '}
          </Text>
          <Box flexDirection="column" flexGrow={1}>
            <MultiLineTextInput
              value={input}
              onChange={onInputChange}
              onSubmit={onSubmit}
              placeholder="Ask anything..."
              focus={true}
            />
          </Box>
        </Box>
      </Box>
    );
  },
);
