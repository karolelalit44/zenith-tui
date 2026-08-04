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

function formatWindowsPath(path: string): string {
  if (!path) return '';
  return path.replace(/\//g, '\\');
}

interface ParsedDiffLine {
  lineNum?: number;
  type: 'add' | 'remove' | 'normal';
  content: string;
}

function parseDiffLines(rawText: string, defaultStartLine: number = 1): ParsedDiffLine[] {
  if (!rawText) return [];
  const lines = rawText.split('\n');
  const result: ParsedDiffLine[] = [];
  let currentLine = defaultStartLine;

  for (const line of lines) {
    const hunkMatch = line.match(/^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@/);
    if (hunkMatch) {
      currentLine = parseInt(hunkMatch[1], 10);
      continue;
    }

    if (line.startsWith('-') && !line.startsWith('---')) {
      result.push({
        lineNum: currentLine,
        type: 'remove',
        content: line.startsWith('- ') ? line.slice(2) : line.slice(1),
      });
    } else if (line.startsWith('+') && !line.startsWith('+++')) {
      result.push({
        lineNum: currentLine,
        type: 'add',
        content: line.startsWith('+ ') ? line.slice(2) : line.slice(1),
      });
      currentLine++;
    } else {
      const clean = line.startsWith(' ') ? line.slice(1) : line;
      result.push({
        lineNum: currentLine,
        type: 'normal',
        content: clean,
      });
      currentLine++;
    }
  }

  return result;
}

function FileToolResult({ event, theme }: { event: ToolResultEvent; theme: ThemeType }) {
  const rawPath = String(event.metadata.path || event.metadata.filepath || '');
  const winPath = formatWindowsPath(rawPath);
  const addedLines = typeof event.metadata.added_lines === 'number' ? event.metadata.added_lines : undefined;
  const removedLines = typeof event.metadata.removed_lines === 'number' ? event.metadata.removed_lines : undefined;
  const startLine = typeof event.metadata.start_line === 'number' ? event.metadata.start_line : 1;

  const parts: string[] = [];
  if (removedLines) parts.push(`Removed ${removedLines} ${removedLines === 1 ? 'line' : 'lines'}`);
  if (addedLines) parts.push(`Added ${addedLines} ${addedLines === 1 ? 'line' : 'lines'}`);
  const statsStr = parts.join(', ');

  const rawDiff = String(event.metadata.diff || event.metadata.diff_content || event.output || '');
  const parsedLines = parseDiffLines(rawDiff, startLine);

  const MAX_LINES = 15;
  const isTruncated = parsedLines.length > MAX_LINES;
  const visibleLines = isTruncated ? parsedLines.slice(0, MAX_LINES) : parsedLines;

  const maxLineNum = parsedLines.reduce((max, l) => Math.max(max, l.lineNum || 0), 1);
  const gutterWidth = Math.max(2, String(maxLineNum).length);

  return (
    <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
      {}
      <Box flexDirection="row" alignItems="center">
        <Text color={theme.colors.status.success} bold>
          ●{' '}
        </Text>
        <Text color={event.success ? theme.colors.status.success : theme.colors.status.error} bold>
          Update({winPath})
        </Text>
      </Box>

      {}
      <Box flexDirection="row" alignItems="center" paddingLeft={1}>
        <Text color={theme.colors.text.dim}>└ </Text>
        <Text color={theme.colors.text.dim}>{statsStr || 'Updated file'}</Text>
      </Box>

      {}
      {visibleLines.length > 0 && (
        <Box flexDirection="column" paddingLeft={3} marginTop={0}>
          {visibleLines.map((line, idx) => {
            const numStr =
              line.lineNum !== undefined
                ? String(line.lineNum).padStart(gutterWidth, ' ')
                : ''.padStart(gutterWidth, ' ');
            if (line.type === 'remove') {
              return (
                <Box key={idx} backgroundColor={theme.colors.diff.removeBg} width="100%">
                  <Text color={theme.colors.text.dim}>{numStr} </Text>
                  <Text color={theme.colors.diff.removeFg}>{line.content}</Text>
                </Box>
              );
            }
            if (line.type === 'add') {
              return (
                <Box key={idx} backgroundColor={theme.colors.diff.addBg} width="100%">
                  <Text color={theme.colors.text.dim}>{numStr} </Text>
                  <Text color={theme.colors.diff.addFg}>{line.content}</Text>
                </Box>
              );
            }
            return (
              <Box key={idx} width="100%">
                <Text color={theme.colors.text.dim}>{numStr} </Text>
                <Text color={theme.colors.text.bright}>{line.content}</Text>
              </Box>
            );
          })}
          {isTruncated && (
            <Text color={theme.colors.text.dim} italic>
              ... [{parsedLines.length - MAX_LINES} more lines]
            </Text>
          )}
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
    const rawPath = String(event.metadata.path || event.metadata.filepath || '');
    const winPath = formatWindowsPath(rawPath);
    const lines = event.output ? event.output.split('\n') : [];
    const MAX_READ_LINES = 8;
    const isTruncated = lines.length > MAX_READ_LINES;
    const visibleLines = isTruncated ? lines.slice(0, MAX_READ_LINES) : lines;
    const gutterWidth = Math.max(2, String(lines.length).length);

    return (
      <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
        <Box flexDirection="row" alignItems="center">
          <Text color={theme.colors.status.success} bold>
            ●{' '}
          </Text>
          <Text color={theme.colors.status.success} bold>
            Read({winPath})
          </Text>
        </Box>
        <Box flexDirection="row" alignItems="center" paddingLeft={1}>
          <Text color={theme.colors.text.dim}>└ </Text>
          <Text color={theme.colors.text.dim}>
            {lines.length} {lines.length === 1 ? 'line' : 'lines'}
          </Text>
        </Box>
        {visibleLines.length > 0 && (
          <Box flexDirection="column" paddingLeft={3} marginTop={0}>
            {visibleLines.map((lineContent, lineIdx) => {
              const numStr = String(lineIdx + 1).padStart(gutterWidth, ' ');
              return (
                <Box key={lineIdx} width="100%">
                  <Text color={theme.colors.text.dim}>{numStr} </Text>
                  <Text color={theme.colors.text.bright}>{lineContent}</Text>
                </Box>
              );
            })}
            {isTruncated && (
              <Text color={theme.colors.text.dim} italic>
                ... [{lines.length - MAX_READ_LINES} more lines]
              </Text>
            )}
          </Box>
        )}
      </Box>
    );
  }

  return <DefaultResult event={event} theme={theme} />;
});
