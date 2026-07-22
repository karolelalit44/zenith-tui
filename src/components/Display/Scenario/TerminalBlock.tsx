import React, { useState, useEffect } from 'react';
import { Box, Text } from 'ink';
import { useTheme } from '../../../theme/ThemeContext';
import { TerminalEvent } from '../../../types/scenario';

interface TerminalBlockProps {
  event: TerminalEvent;
  isHistorical?: boolean;
}

export const TerminalBlock: React.FC<TerminalBlockProps> = React.memo(({ event }) => {
  const { theme } = useTheme();

  return (
    <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
      {/* Command Line Header */}
      <Box flexDirection="row" alignItems="center" marginBottom={1} flexWrap="wrap">
        <Text color="#58A6FF" bold>[COMMAND PROMPT]</Text>
        <Text color={theme.colors.text.muted}> </Text>
        <Text color="#58A6FF" bold>$ </Text>
        <Text color="#E6EDF3" bold>{event.command}</Text>
        <Text color="#8B949E"> ({(event.duration / 1000).toFixed(1)}s)</Text>
      </Box>

      {/* Terminal Output Box */}
      <Box flexDirection="column" width="100%" borderStyle="round" borderColor="#30363D" paddingX={1}>
        {event.output.length > 0 ? (
          event.output.map((line, idx) => (
            <Text key={idx} color="#C9D1D9" wrap="wrap">
              {line}
            </Text>
          ))
        ) : (
          <Text color="#8B949E">(command executed silently)</Text>
        )}

        <Box marginTop={1} flexDirection="row" justifyContent="flex-end">
          <Text color="#3FB950" bold>[EXIT CODE 0]</Text>
        </Box>
      </Box>
    </Box>
  );
});
