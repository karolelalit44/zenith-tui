import { Box, Text } from 'ink';
import React from 'react';
import { useTheme } from '../../../theme/ThemeContext';
import type { PlanReadyEvent } from '../../../types/scenario';
import { TerminalMarkdown } from './TerminalMarkdown';

interface PlanReadyBlockProps {
  event: PlanReadyEvent;
}

export const PlanReadyBlock: React.FC<PlanReadyBlockProps> = React.memo(({ event }) => {
  const { theme } = useTheme();
  const hasPlan = Boolean(event.plan && event.plan.trim().length > 0);

  return (
    <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
      <Box flexDirection="row" alignItems="center" marginBottom={hasPlan ? 1 : 0}>
        <Text color={theme.colors.status.warning} bold>
          ◈
        </Text>
        <Text color={theme.colors.text.bright} bold>
          {' '}
          Plan ready
        </Text>
        <Text color={theme.colors.text.dim}> — awaiting approval before building</Text>
      </Box>
      {hasPlan && (
        <Box paddingLeft={1} flexDirection="column">
          <TerminalMarkdown content={event.plan} />
        </Box>
      )}
    </Box>
  );
});
