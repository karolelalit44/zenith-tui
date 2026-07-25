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

  const modeBadge =
    mode === 'plan'
      ? { label: '[PLAN]', color: theme.colors.status.accent }
      : { label: '[BUILD]', color: theme.colors.status.success };

  return (
    <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
      <Box
        flexDirection="row"
        alignItems="center"
        width="100%"
        paddingX={1}
        paddingY={0}
        backgroundColor={theme.colors.bg.modal}
      >
        <Text color={modeBadge.color} bold>
          {modeBadge.label}
        </Text>
        <Text color={theme.colors.text.muted}> </Text>
        <Text color={theme.colors.text.bright} bold>
          {prompt}
        </Text>
      </Box>
      <Box flexDirection="row" justifyContent="flex-end" marginTop={0}>
        <Text color={theme.colors.text.dim}>{timeStr}</Text>
      </Box>
    </Box>
  );
};
