import { Box, Text, useInput } from 'ink';
import React, { useState } from 'react';
import { useTheme } from '../../../theme/ThemeContext';
import type { WarningEvent } from '../../../types/scenario';
import { MAX_MESSAGE_PREVIEW_LENGTH } from '../../../utils/text';

interface WarningBlockProps {
  event: WarningEvent;
}

export const WarningBlock: React.FC<WarningBlockProps> = React.memo(({ event }) => {
  const { theme } = useTheme();
  const [expanded, setExpanded] = useState(false);

  const rawMessage = event.message.trim();
  const truncated = rawMessage.length > MAX_MESSAGE_PREVIEW_LENGTH;
  const shownMessage = expanded || !truncated ? rawMessage : `${rawMessage.slice(0, MAX_MESSAGE_PREVIEW_LENGTH)}…`;

  useInput(
    (input, key) => {
      if (key.ctrl && (input === 'd' || input === '\x04')) {
        setExpanded((value) => !value);
      }
    },
    { isActive: truncated },
  );

  return (
    <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
      <Box flexDirection="row" alignItems="center">
        <Text color={theme.colors.status.warning} bold>
          ▲ [WARNING]{' '}
        </Text>
        <Text color={theme.colors.text.bright} wrap="wrap">
          {shownMessage}
        </Text>
        {event.code && <Text color={theme.colors.text.dim}> ({event.code})</Text>}
      </Box>
      {truncated && (
        <Box paddingLeft={1}>
          <Text color={theme.colors.text.muted}>
            {expanded ? '(ctrl+d to hide full details)' : '… (ctrl+d to show full details)'}
          </Text>
        </Box>
      )}
    </Box>
  );
});
