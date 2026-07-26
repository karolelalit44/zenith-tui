import { Box, Text } from 'ink';
import React from 'react';
import { useTheme } from '../../../theme/ThemeContext';
import type { ToolResultEvent } from '../../../types/scenario';
import type { EventRenderContext } from './componentRegistry';

type ThemeType = ReturnType<typeof useTheme>['theme'];

interface ToolResultCardProps {
  event: ToolResultEvent;
  context?: EventRenderContext;
}

function BashResult({ event, theme }: { event: ToolResultEvent; theme: ThemeType }) {
  const command = String(event.metadata.command || '');
  const outputLines: string[] = Array.isArray(event.metadata.output_lines)
    ? event.metadata.output_lines.map(String)
    : typeof event.metadata.output === 'string'
      ? event.metadata.output.split('\n')
      : [];
  const exitCode = typeof event.metadata.exit_code === 'number' ? event.metadata.exit_code : undefined;
  const duration = typeof event.metadata.duration_ms === 'number' ? event.metadata.duration_ms : undefined;

  const cleanedOutput = outputLines
    .map((l) => l.replace(/\r/g, ''))
    .filter((l) => l.trim().length > 0);

  const width = Math.min(process.stdout.columns ?? 80, 80) - 4;

  return (
    <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
      <Box flexDirection="row" alignItems="center" marginBottom={0}>
        <Text color={event.success ? theme.colors.status.success : theme.colors.status.error} bold>
          {event.success ? '✓ [RUN]' : '✗ [RUN]'}
        </Text>
        <Text color={theme.colors.text.muted}> $ </Text>
        <Text color={theme.colors.text.bright} bold>
          {command}
        </Text>
      </Box>

      <Box flexDirection="column" width="100%">
        <Box flexDirection="row">
          <Text color={theme.colors.border.muted}>{'┌─'}</Text>
          <Text color={theme.colors.text.dim} bold>{' terminal '}</Text>
          <Text color={theme.colors.border.muted}>{'─'.repeat(Math.max(0, width - 14))}</Text>
          <Text color={theme.colors.border.muted}>{'┐'}</Text>
        </Box>

        {cleanedOutput.length > 0 ? (
          cleanedOutput.slice(0, 50).map((line, idx) => (
            <Box key={idx} flexDirection="row" width="100%">
              <Text color={theme.colors.border.muted}>{'│'}</Text>
              <Text color={theme.colors.code.output} wrap="wrap">{' '}{line}</Text>
            </Box>
          ))
        ) : (
          <Box flexDirection="row" width="100%">
            <Text color={theme.colors.border.muted}>{'│'}</Text>
            <Text color={theme.colors.text.muted} italic>{'  (no output)'}</Text>
          </Box>
        )}

        {outputLines.length > 50 && (
          <Box flexDirection="row" width="100%">
            <Text color={theme.colors.border.muted}>{'│'}</Text>
            <Text color={theme.colors.text.muted}>{'  ... '}{outputLines.length - 50} more lines</Text>
          </Box>
        )}

        <Box flexDirection="row" width="100%">
          <Text color={theme.colors.border.muted}>{'├─'}</Text>
          <Text
            color={event.success ? theme.colors.status.success : theme.colors.status.error}
            bold
          >
            {` exit ${exitCode ?? 0} `}
          </Text>
          {duration !== undefined && (
            <Text color={theme.colors.text.dim}>{(duration / 1000).toFixed(1)}s</Text>
          )}
          <Text color={theme.colors.border.muted}>{'─'.repeat(Math.max(0, width - 20))}</Text>
          <Text color={theme.colors.border.muted}>{'┘'}</Text>
        </Box>
      </Box>
    </Box>
  );
}

function FileToolResult({ event, theme }: { event: ToolResultEvent; theme: ThemeType }) {
  const path = String(event.metadata.path || event.metadata.filepath || '');
  const fileName = path.split('/').pop() || path;

  return (
    <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
      <Box flexDirection="row" alignItems="center">
        <Text color={event.success ? theme.colors.status.success : theme.colors.status.error} bold>
          {event.success ? '✓' : '✗'} [{event.tool.toUpperCase()}]{' '}
        </Text>
        <Text color={theme.colors.text.bright}>{fileName}</Text>
      </Box>
      {path && (
        <Box paddingLeft={3}>
          <Text color={theme.colors.text.muted}>{path}</Text>
        </Box>
      )}
    </Box>
  );
}

function DefaultResult({ event, theme }: { event: ToolResultEvent; theme: ThemeType }) {
  const outputPreview = event.output
    ? event.output.split('\n').slice(0, 10).join('\n')
    : '';

  return (
    <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
      <Box flexDirection="row" alignItems="center">
        <Text color={event.success ? theme.colors.status.success : theme.colors.status.error} bold>
          {event.success ? '✓' : '✗'} [{event.tool.toUpperCase()}]{' '}
        </Text>
        <Text color={theme.colors.text.bright}>
          {event.success ? 'Completed' : 'Failed'}
        </Text>
        {event.error && (
          <Text color={theme.colors.status.error}> - {event.error}</Text>
        )}
      </Box>
      {outputPreview && (
        <Box paddingLeft={3} marginTop={0}>
          <Text color={theme.colors.text.muted} wrap="wrap">
            {outputPreview}
            {event.output.split('\n').length > 10 && ' ...'}
          </Text>
        </Box>
      )}
      {event.truncated && (
        <Box paddingLeft={3}>
          <Text color={theme.colors.text.muted} italic>(output truncated)</Text>
        </Box>
      )}
    </Box>
  );
}

export const ToolResultCard: React.FC<ToolResultCardProps> = React.memo(({ event }) => {
  const { theme } = useTheme();
  const tool = event.tool;

  if (tool === 'bash' || tool === 'execute' || tool === 'run_command') {
    return <BashResult event={event} theme={theme} />;
  }

  if (tool === 'file_write' || tool === 'file_edit' || tool === 'file_delete') {
    return <FileToolResult event={event} theme={theme} />;
  }

  if (tool === 'file_read') {
    const path = String(event.metadata.path || event.metadata.filepath || '');
    const fileName = path.split('/').pop() || path;
    const lines = event.output ? event.output.split('\n') : [];
    const preview = lines.slice(0, 30).join('\n');

    return (
      <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
        <Box flexDirection="row" alignItems="center">
          <Text color={theme.colors.status.success} bold>
            ✓ [FILE_READ]{' '}
          </Text>
          <Text color={theme.colors.text.bright}>{fileName}</Text>
        </Box>
        {preview && (
          <Box
            flexDirection="column"
            width="100%"
            borderStyle="round"
            borderColor={theme.colors.text.muted}
            paddingX={1}
            marginTop={0}
          >
            {lines.slice(0, 30).map((line, i) => (
              <Text key={i} color={theme.colors.text.bright} wrap="wrap">
                {line}
              </Text>
            ))}
            {lines.length > 30 && (
              <Text color={theme.colors.text.muted}>
                ... ({lines.length - 30} more lines)
              </Text>
            )}
          </Box>
        )}
      </Box>
    );
  }

  return <DefaultResult event={event} theme={theme} />;
});
