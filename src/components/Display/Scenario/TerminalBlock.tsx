import React, { useState, useEffect } from 'react';
import { Box, Text } from 'ink';
import { useTheme } from '../../../theme/ThemeContext';
import { TerminalEvent } from '../../../types/scenario';

interface TerminalBlockProps {
  event: TerminalEvent;
  isHistorical?: boolean;
}

interface TerminalBlockProps {
  event: TerminalEvent;
  isHistorical?: boolean;
}

export const TerminalBlock: React.FC<TerminalBlockProps> = React.memo(({ event }) => {
  const { theme } = useTheme();

  return (
    <Box flexDirection="column" marginBottom={1} paddingX={1}>
      {/* Command Line Header */}
      <Box flexDirection="row" alignItems="center" marginBottom={1}>
        <Text color="#58A6FF" bold>$ </Text>
        <Text color="#E6EDF3" bold>{event.command}</Text>
        <Text color={theme.colors.text.muted}> ({(event.duration / 1000).toFixed(1)}s)</Text>
      </Box>

      {/* Terminal Output */}
      {event.output.length > 0 && (
        <Box flexDirection="column" paddingLeft={2}>
          {event.output.map((line, idx) => (
            <Text key={idx} color="#C9D1D9">{line}</Text>
          ))}
        </Box>
      )}
    </Box>
  );
});
