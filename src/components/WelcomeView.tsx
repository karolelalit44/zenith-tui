import { Box, Text } from 'ink';
import React from 'react';
import { useTheme } from '../theme/ThemeContext';

interface WelcomeViewProps {
  workspace: string;
}

const SUGGESTIONS = [
  'Help me understand this codebase',
  'Run the test suite and show results',
  'Create a new module with proper structure',
];

export const WelcomeView: React.FC<WelcomeViewProps> = ({ workspace }) => {
  const { theme } = useTheme();
  return (
    <Box flexDirection="column" paddingX={1} paddingTop={1} width="100%">
      <Text color={theme.colors.text.muted} bold>
        Try asking:
      </Text>
      <Box flexDirection="column" marginTop={1} paddingLeft={1}>
        {SUGGESTIONS.map((suggestion, idx) => (
          <Box key={idx} flexDirection="row" marginBottom={0}>
            <Text color={theme.colors.status.accent}>{idx + 1}. </Text>
            <Text color={theme.colors.text.ethereal}>{suggestion}</Text>
          </Box>
        ))}
      </Box>
    </Box>
  );
};
