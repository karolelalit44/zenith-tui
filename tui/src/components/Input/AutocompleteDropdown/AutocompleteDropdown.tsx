import { Box, Text, useInput } from 'ink';
import React, { useState } from 'react';
import { useTerminalDimensions } from '../../../hooks/useTerminalDimensions';
import { commandRegistry } from '../../../services/api/CommandRegistry';
import { useTheme } from '../../../theme/ThemeContext';
import type { AutocompleteDropdownProps } from './types';

interface CommandEntry {
  command: string;
  description: string;
}

const COMMAND_LIST: CommandEntry[] = commandRegistry
  .filter((c) => c.slash)
  .map((c) => ({ command: c.slash as string, description: c.description }));

export const AutocompleteDropdown: React.FC<AutocompleteDropdownProps> = ({
  input,
  onSelect,
  onClose,
  onQueryChange,
}) => {
  const { theme } = useTheme();
  const { rows } = useTerminalDimensions();
  const [activeIndex, setActiveIndex] = useState(0);

  const query = input.startsWith('/') ? input.slice(1) : input;
  const queryLower = query.toLowerCase();
  const filtered = COMMAND_LIST.filter(
    (c) => c.command.slice(1).toLowerCase().includes(queryLower) || c.description.toLowerCase().includes(queryLower),
  );

  const maxVisible = Math.max(3, Math.min(6, rows - 10));
  const visibleItems = filtered.slice(0, maxVisible);

  const [lastQuery, setLastQuery] = useState(query);
  if (lastQuery !== query) {
    setLastQuery(query);
    setActiveIndex(0);
  }

  useInput((char, key) => {
    if (key.escape) {
      onClose();
      return;
    }
    if (key.upArrow) {
      setActiveIndex((prev) => Math.max(0, prev - 1));
      return;
    }
    if (key.downArrow) {
      setActiveIndex((prev) => Math.min(visibleItems.length - 1, prev + 1));
      return;
    }
    if (key.return || char === '\n' || char === '\r') {
      const entry = visibleItems[activeIndex];
      if (entry) onSelect(entry.command);
      return;
    }
    if (key.tab) {
      const entry = visibleItems[activeIndex] ?? visibleItems[0];
      if (entry && onQueryChange) onQueryChange(entry.command);
      return;
    }
  });

  if (filtered.length === 0) {
    return (
      <Box flexDirection="column" paddingX={1}>
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
    >
      <Box flexDirection="row" alignItems="center" marginBottom={1}>
        <Text color={theme.colors.status.accent} bold wrap="truncate-end">
          [SLASH COMMANDS]
        </Text>
        <Text color={theme.colors.text.muted} wrap="truncate-end">
          {' '}
          — ↑/↓ navigate · Enter select · Tab complete · Esc close
        </Text>
      </Box>

      {visibleItems.map((cmd, i) => {
        const isActive = i === activeIndex;
        return (
          <Box key={cmd.command} flexDirection="row" alignItems="center" width="100%">
            <Box width={2} flexShrink={0}>
              <Text color={isActive ? theme.colors.status.success : theme.colors.text.muted}>
                {isActive ? '▸' : ' '}
              </Text>
            </Box>
            <Box width={16} flexShrink={0}>
              <Text color={isActive ? theme.colors.status.info : theme.colors.text.bright} bold={isActive} wrap="truncate-end">
                {cmd.command}
              </Text>
            </Box>
            <Box flexShrink={1} overflow="hidden">
              <Text color={isActive ? theme.colors.text.bright : theme.colors.text.muted} wrap="truncate-end">{cmd.description}</Text>
            </Box>
          </Box>
        );
      })}
    </Box>
  );
};
