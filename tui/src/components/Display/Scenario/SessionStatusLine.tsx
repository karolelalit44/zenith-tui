import { Box, Text } from 'ink';
import React from 'react';
import { useTheme } from '../../../theme/ThemeContext';
import type { ContextUpdatedEvent, SessionInfoEvent, TokenUsageRecordedEvent } from '../../../types/scenario';
import { formatRunTokens } from '../../../utils/footerLayout';

interface SessionStatusLineProps {
  event: SessionInfoEvent | ContextUpdatedEvent | TokenUsageRecordedEvent;
}

/**
 * Operational session/context/token status line. These are backend housekeeping
 * signals (session transitions, context occupancy snapshots, provider-billed
 * token rows), rendered as single dim status rows — never prominent cards.
 */
export const SessionStatusLine: React.FC<SessionStatusLineProps> = React.memo(({ event }) => {
  const { theme } = useTheme();

  let prefix = '';
  let detail = '';
  let accent = theme.colors.text.dim;

  if (event.kind === 'context_updated') {
    prefix = 'context';
    detail = `${formatRunTokens(event.used)}/${formatRunTokens(event.total)} (${event.percent}%)`;
    accent = theme.colors.status.info;
  } else if (event.kind === 'token_usage_recorded') {
    prefix = 'tokens';
    detail = `${formatRunTokens(event.totalTokens)}${typeof event.totalCost === 'number' && event.totalCost > 0 ? ` · $${event.totalCost.toFixed(4)}` : ''}`;
    accent = theme.colors.status.info;
  } else {
    prefix = event.kind.replace(/^session_/, '').replace(/_/g, ' ');
    detail = event.message.replace(/^Session [A-Z][a-z ]+:\s*/, '');
  }

  return (
    <Box flexDirection="row" width="100%" marginBottom={0} paddingX={1}>
      <Box flexShrink={0}>
        <Text color={accent} bold>
          {prefix}:{' '}
        </Text>
      </Box>
      <Box flexShrink={0}>
        <Text color={theme.colors.text.dim}>{detail}</Text>
      </Box>
      {event.kind === 'session_error' && (
        <Box marginLeft={1} flexShrink={0}>
          <Text color={theme.colors.status.error}>[error]</Text>
        </Box>
      )}
    </Box>
  );
});

SessionStatusLine.displayName = 'SessionStatusLine';
