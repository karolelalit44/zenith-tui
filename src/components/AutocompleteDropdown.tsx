import React, { useState } from 'react';
import { Box, Text, useInput } from 'ink';
import { theme } from '../theme/theme';

interface CommandHint {
  command: string;
  description: string;
}

const mockCommands: CommandHint[] = [
  { command: '/add-dir', description: 'Add a new working directory' },
  { command: '/agents', description: 'Manage agent configurations' },
  { command: '/bashes', description: 'List and manage background tasks' },
  { command: '/clear (reset, new)', description: 'Clear conversation history and free up context' },
  { command: '/compact', description: 'Clear conversation history but keep a summary in context' },
  { command: '/help', description: 'Show available commands' },
  { command: '/build', description: 'Run the mock production build sequence' },
  { command: '/context', description: 'View the current file context window' },
  { command: '/persona', description: 'Switch the active agent persona' },
  { command: '/plugin', description: 'Manage Zenith plugins and extensions' },
  { command: '/settings', description: 'Configure Zenith options and theme' },
];

export const AutocompleteDropdown: React.FC<{ input: string; onSelect: (cmd: string) => void }> = ({ input, onSelect }) => {
  const [activeIndex, setActiveIndex] = useState(0);

  const filtered = mockCommands.filter(c => c.command.startsWith(input));

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
        <Text color={theme.colors.border.muted}>{'─'.repeat(100)}</Text>
      </Box>
      {filtered.map((cmd, i) => (
        <Box key={i} flexDirection="row">
          <Box width={25}>
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
