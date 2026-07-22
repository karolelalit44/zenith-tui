import React, { useState } from 'react';
import { Box, Text, useInput } from 'ink';
import { useTheme } from '../../../theme/ThemeContext';
import { AutocompleteDropdownProps } from './types';
import { COMMAND_LIST } from '../data/commands';
import { UI_CONSTANTS } from '../../../constants';

export const AutocompleteDropdown: React.FC<AutocompleteDropdownProps> = ({ input, onSelect }) => {
  const { theme } = useTheme();
  const [activeIndex, setActiveIndex] = useState(0);

  const filtered = COMMAND_LIST.filter(c => c.command.startsWith(input));

  useInput((char, key) => {
    if (filtered.length === 0) return;
    if (key.upArrow) {
      setActiveIndex(prev => Math.max(0, prev - 1));
    } else if (key.downArrow) {
      setActiveIndex(prev => Math.min(filtered.length - 1, prev + 1));
    } else if (key.return) {
      onSelect(filtered[activeIndex]?.command || '');
    }
  });

  if (filtered.length === 0) {
    return (
      <Box flexDirection="column" marginTop={1}>
        <Text color={theme.colors.text.muted}>No matching commands.</Text>
      </Box>
    );
  }

  return (
    <Box flexDirection="column">
      <Box marginBottom={1}>
        <Text color={theme.colors.border.muted}>{'─'.repeat(UI_CONSTANTS.SEPARATOR_WIDTH)}</Text>
      </Box>
      {filtered.map((cmd, i) => (
        <Box key={i} flexDirection="row">
          <Box width={UI_CONSTANTS.AUTOCOMPLETE_COMMAND_WIDTH}>
            <Text color={i === activeIndex ? theme.colors.text.ethereal : theme.colors.text.muted} bold={i === activeIndex}>
              {cmd.command}
            </Text>
          </Box>
          <Box>
            <Text color={i === activeIndex ? theme.colors.text.emerald : theme.colors.text.muted}>
              {cmd.description}
            </Text>
          </Box>
        </Box>
      ))}
    </Box>
  );
};
