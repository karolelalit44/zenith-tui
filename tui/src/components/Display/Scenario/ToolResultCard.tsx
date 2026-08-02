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

  const cleanedOutput = outputLines.map((l) => l.replace(/\r/g, '')).filter((l) => l.trim().length > 0);

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
        {duration !== undefined && <Text color={theme.colors.text.dim}> ({(duration / 1000).toFixed(1)}s)</Text>}
      </Box>

      {cleanedOutput.length > 0 && (
        <Box flexDirection="column" paddingLeft={3} marginTop={0}>
          {cleanedOutput.slice(0, 20).map((line, idx) => (
            <Text key={idx} color={theme.colors.code.output} wrap="wrap">
              {line}
            </Text>
          ))}
          {outputLines.length > 20 && (
            <Text color={theme.colors.text.muted}>... {outputLines.length - 20} more lines</Text>
          )}
        </Box>
      )}

      {!event.success && exitCode !== undefined && (
        <Box paddingLeft={3}>
          <Text color={theme.colors.status.error}>exit code: {exitCode}</Text>
        </Box>
      )}
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
  const outputPreview = event.output ? event.output.split('\n').slice(0, 10).join('\n') : '';

  return (
    <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
      <Box flexDirection="row" alignItems="center">
        <Text color={event.success ? theme.colors.status.success : theme.colors.status.error} bold>
          {event.success ? '✓' : '✗'} [{event.tool.toUpperCase()}]{' '}
        </Text>
        <Text color={theme.colors.text.bright}>{event.success ? 'Completed' : 'Failed'}</Text>
        {event.error && <Text color={theme.colors.status.error}> - {event.error}</Text>}
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
          <Text color={theme.colors.text.muted} italic>
            (output truncated)
          </Text>
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

    return (
      <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
        <Box flexDirection="row" alignItems="center">
          <Text color={theme.colors.status.success} bold>
            ✓ [FILE_READ]{' '}
          </Text>
          <Text color={theme.colors.text.bright}>{fileName}</Text>
        </Box>
        {path && (
          <Box paddingLeft={3}>
            <Text color={theme.colors.text.muted} dimColor>
              {path}
            </Text>
          </Box>
        )}
        {lines.length > 0 && (
          <Box paddingLeft={3} marginTop={0}>
            <Text color={theme.colors.text.dim}>({lines.length} lines)</Text>
          </Box>
        )}
      </Box>
    );
  }

  return <DefaultResult event={event} theme={theme} />;
});
