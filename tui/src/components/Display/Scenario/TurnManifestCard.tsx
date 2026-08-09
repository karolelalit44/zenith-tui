import { Box, Text } from 'ink';
import React from 'react';
import { useTheme } from '../../../theme/ThemeContext';
import type { TurnManifestEvent } from '../../../types/scenario';
import { formatBytes } from '../../../utils/text';

interface TurnManifestCardProps {
  event: TurnManifestEvent;
}

const MAX_FILES = 8;

export function formatTurnSummary(event: TurnManifestEvent): string {
  if (event.created.length === 0 && event.modified.length === 0 && event.remaining.length === 0) {
    return 'no changes';
  }
  const parts: string[] = [];
  if (event.created.length > 0) parts.push(`${event.created.length} created`);
  if (event.modified.length > 0) parts.push(`${event.modified.length} modified`);
  if (event.completed) {
    parts.push('complete');
  } else {
    parts.push(`${event.remaining.length} remaining`);
  }
  return parts.join(' · ');
}

function FileList({
  files,
  icon,
  statusColor,
  theme,
}: {
  files: { path: string; size?: number }[];
  icon: string;
  statusColor: string;
  theme: ReturnType<typeof useTheme>['theme'];
}) {
  if (files.length === 0) return null;
  const shown = files.slice(0, MAX_FILES);
  const hidden = files.length - shown.length;

  return (
    <Box flexDirection="column" width="100%">
      <Box flexDirection="row">
        <Box width={2}>
          <Text color={statusColor}>{icon}</Text>
        </Box>
        <Text color={theme.colors.text.bright} bold>
          {files.length} {files.length === 1 ? 'file' : 'files'}
        </Text>
      </Box>
      {shown.map((file) => (
        <Box key={file.path} flexDirection="row" paddingLeft={2}>
          <Box flexGrow={1} flexShrink={1}>
            <Text color={theme.colors.text.ethereal}>{file.path}</Text>
          </Box>
          {typeof file.size === 'number' && file.size >= 0 && (
            <Text color={theme.colors.text.dim}>{formatBytes(file.size)}</Text>
          )}
        </Box>
      ))}
      {hidden > 0 && (
        <Box paddingLeft={2}>
          <Text color={theme.colors.text.muted}>… {hidden} more</Text>
        </Box>
      )}
    </Box>
  );
}

export const TurnManifestCard: React.FC<TurnManifestCardProps> = React.memo(({ event }) => {
  const { theme } = useTheme();

  const createdFiles = event.files.filter((f) => event.created.includes(f.path));
  // The server only reports sizes for created files (loop.py `_build_manifest`),
  // so modified paths are rendered from the manifest's `modified` list alone.
  const modifiedFiles = event.modified.map((path) => ({ path }));

  return (
    <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
      <Box
        flexDirection="row"
        alignItems="center"
        borderStyle="round"
        borderColor={theme.colors.border.default}
        paddingX={1}
        paddingY={0}
      >
        <Text color={event.completed ? theme.colors.status.success : theme.colors.status.warning} bold>
          {event.completed ? '✓ Turn complete' : event.stalled ? '● Turn stalled' : '⧗ Turn paused'}
        </Text>
        <Text color={theme.colors.text.muted}> </Text>
        <Text color={theme.colors.text.muted}>{formatTurnSummary(event)}</Text>
      </Box>

      {(event.created.length > 0 || event.modified.length > 0) && (
        <Box flexDirection="column" paddingLeft={1} paddingTop={1} width="100%">
          <FileList files={createdFiles} icon="+" statusColor={theme.colors.status.success} theme={theme} />
          <FileList files={modifiedFiles} icon="✎" statusColor={theme.colors.status.info} theme={theme} />
        </Box>
      )}

      {event.remaining.length > 0 && (
        <Box flexDirection="column" paddingLeft={1} paddingTop={1} width="100%">
          <Box flexDirection="row">
            <Box width={2}>
              <Text color={theme.colors.status.warning}>◈</Text>
            </Box>
            <Text color={theme.colors.text.bright} bold>
              Remaining
            </Text>
          </Box>
          {event.remaining.slice(0, MAX_FILES).map((item, idx) => (
            <Box key={idx} paddingLeft={2}>
              <Text color={theme.colors.text.muted}>- {item}</Text>
            </Box>
          ))}
          {event.remaining.length > MAX_FILES && (
            <Box paddingLeft={2}>
              <Text color={theme.colors.text.muted}>… {event.remaining.length - MAX_FILES} more</Text>
            </Box>
          )}
        </Box>
      )}
    </Box>
  );
});
