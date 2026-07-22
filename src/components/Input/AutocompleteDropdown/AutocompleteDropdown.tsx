import { Box, Text, useInput } from 'ink';
import React, { useState } from 'react';
import { useTheme } from '../../../theme/ThemeContext';
import { COMMAND_LIST } from '../data/commands';
import type { AutocompleteDropdownProps } from './types';

export const AutocompleteDropdown: React.FC<AutocompleteDropdownProps> = ({ input, onSelect }) => {
  const { theme } = useTheme();
  const [activeIndex, setActiveIndex] = useState(0);

  const cleanInput = input.startsWith('/') ? input : `/${input}`;
  const filtered = COMMAND_LIST.filter((c) => c.command.toLowerCase().includes(cleanInput.toLowerCase()));

  useInput((_char, key) => {
    if (filtered.length === 0) return;
    if (key.upArrow) {
      setActiveIndex((prev) => Math.max(0, prev - 1));
    } else if (key.downArrow) {
      setActiveIndex((prev) => Math.min(filtered.length - 1, prev + 1));
    } else if (key.return) {
      onSelect(filtered[activeIndex]?.command || '');
    }
  });

  if (filtered.length === 0) {
    return (
      <Box flexDirection="column" marginTop={1} paddingX={1}>
        <Text color={theme.colors.text.muted}>No matching slash commands.</Text>
      </Box>
    );
  }

  return (
    <Box
      flexDirection="column"
      width="100%"
      borderStyle="round"
      borderColor={theme.colors.status.accent}
      paddingX={1}
      paddingY={1}
      marginTop={1}
    >
      <Box flexDirection="row" alignItems="center" marginBottom={1}>
        <Text color={theme.colors.status.accent} bold>
          [SLASH COMMANDS]
        </Text>
        <Text color={theme.colors.text.muted}> — Type to filter · ↑/↓ navigate · Enter select</Text>
      </Box>

      {filtered.map((cmd, i) => {
        const isActive = i === activeIndex;
        return (
          <Box key={i} flexDirection="row" alignItems="center">
            <Box width={2} flexShrink={0}>
              <Text color={isActive ? theme.colors.status.success : theme.colors.text.muted}>
                {isActive ? '▸' : ' '}
              </Text>
            </Box>
            <Box width={16} flexShrink={0}>
              <Text color={isActive ? theme.colors.status.info : theme.colors.text.bright} bold={isActive}>
                {cmd.command}
              </Text>
            </Box>
            <Box flexShrink={1}>
              <Text color={isActive ? theme.colors.text.bright : theme.colors.text.muted}>{cmd.description}</Text>
            </Box>
          </Box>
        );
      })}
    </Box>
  );
};
