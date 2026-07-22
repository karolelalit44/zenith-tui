import { Box, Text } from 'ink';
import React from 'react';
import { useTheme } from '../../theme/ThemeContext';
import type { ScenarioMode } from '../../types/scenario';

interface PromptHeaderProps {
  prompt: string;
  mode: ScenarioMode;
  timestamp?: string;
}

export const PromptHeader: React.FC<PromptHeaderProps> = ({ prompt, mode, timestamp }) => {
  const { theme } = useTheme();
  const timeStr = timestamp || new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });

  return (
    <Box flexDirection="row" justifyContent="space-between" alignItems="center" width="100%" marginBottom={1}>
      <Box flexDirection="row" alignItems="center">
        <Text color={theme.colors.text.muted}>{'> '}</Text>
        <Text color={theme.colors.text.ethereal} bold>
          {prompt}
        </Text>
        <Text color={theme.colors.text.muted}> </Text>
        <Text color={theme.colors.text.muted}>[{mode}]</Text>
      </Box>
      <Text color={theme.colors.text.muted}>[ {timeStr} ]</Text>
    </Box>
  );
};
