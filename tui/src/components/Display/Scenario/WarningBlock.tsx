import { Box, Text } from 'ink';
import React from 'react';
import { useTheme } from '../../../theme/ThemeContext';
import type { WarningEvent } from '../../../types/scenario';
import { MAX_MESSAGE_PREVIEW_LENGTH } from '../../../utils/text';
import type { EventRenderContext } from './componentRegistry';

interface WarningBlockProps {
  event: WarningEvent;
  context?: EventRenderContext;
}

/**
 * Internal agent-loop diagnostics are operational signals, not user-actionable
 * problems. They render as dim, collapsible status lines instead of alarming
 * warning cards. Real warnings (rate limits, auth, quotas) stay prominent.
 */
const LOOP_DIAGNOSTIC_CODES = new Set([
  'STALL',
  'REJECTED',
  'SKIPPED_CALLS',
  'LOOP_DETECTED',
  'REFLECTION_LIMIT',
  'MAX_ITERATIONS',
  'NO_FILES_CREATED',
  'EMPTY_RESPONSE',
  'INVALID_TOOLS',
  'CONTEXT',
  'CONTEXT_EXHAUSTED',
  'LENGTH_EXCEEDED',
  'DUPLICATE_CALL',
  'DOOM_LOOP',
]);

export function isLoopDiagnostic(code?: string): boolean {
  return Boolean(code && LOOP_DIAGNOSTIC_CODES.has(code.toUpperCase()));
}

/** Compact a loop diagnostic message so the status line reads tersely. */
export function compactDiagnosticMessage(message: string): string {
  return message
    .replace(/^Tool\s+'([^']+)'\s+rejected:\s*/i, '$1 rejected: ')
    .replace(/^Request cancelled.*$/i, 'request cancelled')
    .trim();
}

export const WarningBlock: React.FC<WarningBlockProps> = React.memo(({ event, context }) => {
  const { theme } = useTheme();
  const expanded = context?.expandedWarnings === true;

  const diagnostic = isLoopDiagnostic(event.code);
  const rawMessage = (diagnostic ? compactDiagnosticMessage(event.message) : event.message.trim()).trim();
  const truncated = rawMessage.length > MAX_MESSAGE_PREVIEW_LENGTH;
  const shownMessage = expanded || !truncated ? rawMessage : `${rawMessage.slice(0, MAX_MESSAGE_PREVIEW_LENGTH)}…`;

  if (diagnostic) {
    return (
      <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
        <Box flexDirection="row" width="100%">
          <Box flexShrink={0}>
            <Text color={theme.colors.text.dim}>↳ </Text>
          </Box>
          <Box flexGrow={1} flexShrink={1}>
            <Text color={theme.colors.text.dim} wrap="wrap">
              {shownMessage}
            </Text>
          </Box>
        </Box>
        {truncated && (
          <Box paddingLeft={3}>
            <Text color={theme.colors.text.muted}>
              {expanded ? '(ctrl+e to hide full details)' : '… (ctrl+e to show full details)'}
            </Text>
          </Box>
        )}
      </Box>
    );
  }

  return (
    <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
      <Box flexDirection="row" width="100%">
        <Box flexShrink={0}>
          <Text color={theme.colors.status.warning} bold>
            ▲ [WARNING]{' '}
          </Text>
        </Box>
        <Box flexGrow={1} flexShrink={1}>
          <Text color={theme.colors.text.bright} wrap="wrap">
            {shownMessage}
          </Text>
        </Box>
        {event.code && (
          <Box flexShrink={0}>
            <Text color={theme.colors.text.dim}> ({event.code})</Text>
          </Box>
        )}
      </Box>
      {truncated && (
        <Box paddingLeft={3}>
          <Text color={theme.colors.text.muted}>
            {expanded ? '(ctrl+e to hide full details)' : '… (ctrl+e to show full details)'}
          </Text>
        </Box>
      )}
    </Box>
  );
});

WarningBlock.displayName = 'WarningBlock';
