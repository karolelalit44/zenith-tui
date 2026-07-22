import React from 'react';
import { Box, Text } from 'ink';
import { useTheme } from '../../../theme/ThemeContext';
import { FileDeleteEvent } from '../../../types/scenario';

interface FileDeleteCardProps {
  event: FileDeleteEvent;
}

export const FileDeleteCard: React.FC<FileDeleteCardProps> = ({ event }) => {
  const { theme } = useTheme();

  return (
    <Box flexDirection="column" marginBottom={1} paddingX={1}>
      <Box flexDirection="row" alignItems="center" marginBottom={1}>
        <Text color={theme.colors.text.error} bold>✗ Deleted</Text>
        <Text color={theme.colors.text.muted}> · </Text>
        <Text color={theme.colors.text.ethereal} bold>{event.filePath}</Text>
      </Box>

      {event.lines.length > 0 && (
        <Box flexDirection="column" borderStyle="round" borderColor={theme.colors.text.error} paddingX={1}>
          {event.lines.map((line, idx) => (
            <Box key={idx} flexDirection="row">
              <Box width={4}>
                <Text color={theme.colors.text.muted}>{idx + 1}</Text>
              </Box>
              <Box width={2}>
                <Text color={theme.colors.text.error}>-</Text>
              </Box>
              <Text color={theme.colors.text.error} strikethrough>{line.text}</Text>
            </Box>
          ))}
        </Box>
      )}
    </Box>
  );
};
