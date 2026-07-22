import { Box, Text } from 'ink';
import React from 'react';
import { useTickAnimation } from '../../../hooks/useTickAnimation';
import { useTheme } from '../../../theme/ThemeContext';
import type { WaitingEvent } from '../../../types/scenario';

interface WaitingIndicatorProps {
  event: WaitingEvent;
}

export const WaitingIndicator: React.FC<WaitingIndicatorProps> = React.memo(({ event }) => {
  const { theme } = useTheme();
  const tick = useTickAnimation(250);

  const dots = '.'.repeat(tick % 4);

  return (
    <Box flexDirection="row" marginBottom={1} paddingX={1} alignItems="center">
      <Box width={2}>
        <Text color={theme.colors.text.muted}>{['◷', '◶', '◵', '◴'][tick % 4]}</Text>
      </Box>
      <Text color={theme.colors.text.muted}>
        {event.message}
        {dots}
      </Text>
    </Box>
  );
});
