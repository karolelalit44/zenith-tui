import React, { useState, useEffect } from 'react';
import { Box, Text } from 'ink';
import { useTheme } from '../../../theme/ThemeContext';
import { WaitingEvent } from '../../../types/scenario';

interface WaitingIndicatorProps {
  event: WaitingEvent;
}

export const WaitingIndicator: React.FC<WaitingIndicatorProps> = ({ event }) => {
  const { theme } = useTheme();
  const [tick, setTick] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => setTick(t => t + 1), 250);
    return () => clearInterval(interval);
  }, []);

  const dots = '.'.repeat((tick % 4));

  return (
    <Box flexDirection="row" marginBottom={1} paddingX={1} alignItems="center">
      <Box width={2}>
        <Text color={theme.colors.text.muted}>
          {['◷', '◶', '◵', '◴'][tick % 4]}
        </Text>
      </Box>
      <Text color={theme.colors.text.muted}>{event.message}{dots}</Text>
    </Box>
  );
};
