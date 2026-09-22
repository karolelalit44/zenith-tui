import { Box, Text } from 'ink';
import React from 'react';
import { useTheme } from '../../../theme/ThemeContext';
import type {
  PermissionRequestedEvent,
  PermissionResolvedEvent,
  PermissionScope,
} from '../../../types/scenario';
import { truncateEnd } from '../../../utils/text';

interface PermissionRequestBlockProps {
  event: PermissionRequestedEvent | PermissionResolvedEvent;
}

const SCOPE_LABELS: Record<PermissionScope, string> = {
  read: 'read',
  write: 'write',
  delete: 'delete',
  command: 'command',
  network: 'network',
  crewmate: 'crewmate',
  plan: 'plan',
};

function summarizeParams(params?: Record<string, unknown>): string {
  if (!params || Object.keys(params).length === 0) return '';
  const parts = Object.entries(params)
    .slice(0, 3)
    .map(([key, value]) => {
      const v = typeof value === 'object' ? JSON.stringify(value) : String(value);
      return `${key}=${truncateEnd(v, 40)}`;
    });
  const tail = Object.keys(params).length > 3 ? ` …` : '';
  return parts.join(' ').concat(tail);
}

/**
 * Permission approval card. A `permission_requested` row renders as a bordered
 * prompt (scope + tool + redacted params) while the backend turn is suspended;
 * the interactive approve/deny lives in the App-level OptionBanner. The
 * matching `permission_resolved` row renders as a dim outcome line.
 */
export const PermissionRequestBlock: React.FC<PermissionRequestBlockProps> = React.memo(
  ({ event }) => {
    const { theme } = useTheme();

    if (event.kind === 'permission_resolved') {
      const accent = event.allow ? theme.colors.status.success : theme.colors.status.error;
      return (
        <Box flexDirection="row" width="100%" marginBottom={0} paddingX={1}>
          <Box flexShrink={0}>
            <Text color={accent} bold>
              {event.allow ? 'approved' : 'denied'}
            </Text>
          </Box>
          <Box flexShrink={0}>
            <Text color={theme.colors.text.dim}>
              {' '}
              {event.tool || 'permission'} ({event.scope ? SCOPE_LABELS[event.scope] : ''})
            </Text>
          </Box>
        </Box>
      );
    }

    const scope = SCOPE_LABELS[event.scope] || event.scope;
    const detail = event.label || event.tool || 'permission request';
    const paramsPreview = summarizeParams(event.params);

    return (
      <Box
        flexDirection="column"
        width="100%"
        marginBottom={1}
        paddingX={1}
        borderStyle="single"
        borderColor={theme.colors.status.warning}
        paddingY={0}
      >
        <Box flexDirection="row" alignItems="center">
          <Text color={theme.colors.status.warning} bold>
            ⛛
          </Text>
          <Text color={theme.colors.text.bright} bold>
            {' '}
            Permission required
          </Text>
          <Text color={theme.colors.status.info} bold>
            {' '}
            [{scope}]
          </Text>
          <Box flexGrow={1} />
          <Text color={theme.colors.text.dim}>awaiting approval…</Text>
        </Box>
        <Box flexDirection="row" marginTop={0}>
          <Text color={theme.colors.text.dim}>  {truncateEnd(detail, 120)}</Text>
        </Box>
        {paramsPreview && (
          <Box flexDirection="row" marginTop={0}>
            <Text color={theme.colors.text.dim} wrap="truncate-end">
              {'  '}
              {paramsPreview}
            </Text>
          </Box>
        )}
        {event.reason && (
          <Box flexDirection="row" marginTop={0}>
            <Text color={theme.colors.text.muted} wrap="truncate-end">
              {'  '}
              {event.reason}
            </Text>
          </Box>
        )}
      </Box>
    );
  },
);

PermissionRequestBlock.displayName = 'PermissionRequestBlock';