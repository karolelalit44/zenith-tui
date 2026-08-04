import { Box, Text, useInput } from 'ink';
import React, { useState } from 'react';
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

/**
 * Inline slash-command menu anchored beneath the composer. It is fully driven
 * by the `input` prop (the composer stays mounted and focused; typing edits
 * the input which re-filters this list on every keystroke). This component
 * only reacts to menu navigation keys — everything else is left to the input.
 */
export const AutocompleteDropdown: React.FC<AutocompleteDropdownProps> = ({
  input,
  onSelect,
  onClose,
  onQueryChange,
}) => {
  const { theme } = useTheme();
  const [activeIndex, setActiveIndex] = useState(0);

  const query = input.startsWith('/') ? input.slice(1) : input;
  const queryLower = query.toLowerCase();
  const filtered = COMMAND_LIST.filter(
    (c) => c.command.slice(1).toLowerCase().includes(queryLower) || c.description.toLowerCase().includes(queryLower),
  );

  // Real-time filtering: reset the highlight whenever the query changes.
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
      setActiveIndex((prev) => Math.min(filtered.length - 1, prev + 1));
      return;
    }
    if (key.return || char === '\n' || char === '\r') {
      const entry = filtered[activeIndex];
      if (entry) onSelect(entry.command);
      return;
    }
    if (key.tab) {
      const entry = filtered[activeIndex] ?? filtered[0];
      if (entry && onQueryChange) onQueryChange(entry.command);
      return;
    }
    // Regular characters, backspace, arrows etc. are handled by the still
    // focused input field, which updates `input` and re-filters this list.
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
        <Text color={theme.colors.status.accent} bold>
          [SLASH COMMANDS]
        </Text>
        <Text color={theme.colors.text.muted}>
          {' '}
          — Type to filter · ↑/↓ navigate · Enter select · Tab complete · Esc close
        </Text>
      </Box>

      {filtered.map((cmd, i) => {
        const isActive = i === activeIndex;
        return (
          <Box key={cmd.command} flexDirection="row" alignItems="center">
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
