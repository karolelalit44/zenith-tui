import { Box, Text } from 'ink';
import React from 'react';
import {
  BASH_TOOL,
  EXECUTE_TOOL,
  FILE_DELETE_TOOL,
  FILE_EDIT_TOOL,
  FILE_READ_TOOL,
  FILE_WRITE_TOOL,
  RUN_COMMAND_TOOL,
  TOOL_RESULT_FALLBACK_EDIT_LABEL,
  TOOL_RESULT_MAX_DEFAULT_PREVIEW_LINES,
  TOOL_RESULT_MAX_DIFF_LINES,
  TOOL_RESULT_MAX_OUTPUT_LINES,
  TOOL_RESULT_MAX_READ_PREVIEW_LINES,
  TOOL_VERB_LABELS,
} from '../../../constants/toolDisplay';
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
          {cleanedOutput.slice(0, TOOL_RESULT_MAX_OUTPUT_LINES).map((line, idx) => (
            <Text key={idx} color={theme.colors.code.output} wrap="wrap">
              {line}
            </Text>
          ))}
          {outputLines.length > TOOL_RESULT_MAX_OUTPUT_LINES && (
            <Text color={theme.colors.text.muted}>
              ... {outputLines.length - TOOL_RESULT_MAX_OUTPUT_LINES} more lines
            </Text>
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

function PlainFileOutput({ event, theme }: { event: ToolResultEvent; theme: ThemeType }) {
  const lines = event.output ? event.output.split('\n').filter((l) => l.trim().length > 0) : [];
  if (lines.length === 0) return null;
  return (
    <Box flexDirection="column" paddingLeft={3} marginTop={0}>
      {lines.slice(0, TOOL_RESULT_MAX_OUTPUT_LINES).map((line, idx) => (
        <Text key={idx} color={theme.colors.code.output} wrap="wrap">
          {line}
        </Text>
      ))}
      {lines.length > TOOL_RESULT_MAX_OUTPUT_LINES && (
        <Text color={theme.colors.text.muted}>... {lines.length - TOOL_RESULT_MAX_OUTPUT_LINES} more lines</Text>
      )}
    </Box>
  );
}

function FileEditDiff({ event, theme }: { event: ToolResultEvent; theme: ThemeType }) {
  const startLine = typeof event.metadata.start_line === 'number' ? event.metadata.start_line : 1;
  const rawDiff = String(event.metadata.diff || event.metadata.diff_content || event.output || '');
  const parsedLines = parseDiffLines(rawDiff, startLine);

  if (parsedLines.length === 0) return null;

  const isTruncated = parsedLines.length > TOOL_RESULT_MAX_DIFF_LINES;
  const visibleLines = isTruncated ? parsedLines.slice(0, TOOL_RESULT_MAX_DIFF_LINES) : parsedLines;

  const maxLineNum = parsedLines.reduce((max, l) => Math.max(max, l.lineNum || 0), 1);
  const gutterWidth = Math.max(2, String(maxLineNum).length);

  return (
    <Box flexDirection="column" paddingLeft={3} marginTop={0}>
      {visibleLines.map((line, idx) => {
        const numStr =
          line.lineNum !== undefined ? String(line.lineNum).padStart(gutterWidth, ' ') : ''.padStart(gutterWidth, ' ');
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
          ... [{parsedLines.length - TOOL_RESULT_MAX_DIFF_LINES} more lines]
        </Text>
      )}
    </Box>
  );
}

function FileToolResult({ event, theme }: { event: ToolResultEvent; theme: ThemeType }) {
  const rawPath = String(event.metadata.path || event.metadata.filepath || '');
  const winPath = formatWindowsPath(rawPath);
  const verb = TOOL_VERB_LABELS[event.tool] ?? TOOL_VERB_LABELS[FILE_EDIT_TOOL];
  const statusColor = event.success ? theme.colors.status.success : theme.colors.status.error;

  return (
    <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
      <Box flexDirection="row" alignItems="center">
        <Text color={statusColor} bold>
          ●{' '}
        </Text>
        <Text color={statusColor} bold>
          {verb}({winPath})
        </Text>
      </Box>

      {!event.success && event.error && (
        <Box flexDirection="row" paddingLeft={1}>
          <Text color={theme.colors.status.error} wrap="wrap">
            {event.error}
          </Text>
        </Box>
      )}

      {event.tool === FILE_WRITE_TOOL || event.tool === FILE_DELETE_TOOL ? (
        <PlainFileOutput event={event} theme={theme} />
      ) : (
        <>
          <Box flexDirection="row" alignItems="center" paddingLeft={1}>
            <Text color={theme.colors.text.dim}>└ </Text>
            <Text color={theme.colors.text.dim}>{TOOL_RESULT_FALLBACK_EDIT_LABEL}</Text>
          </Box>
          <FileEditDiff event={event} theme={theme} />
        </>
      )}
    </Box>
  );
}

function DefaultResult({ event, theme }: { event: ToolResultEvent; theme: ThemeType }) {
  const outputPreview = event.output
    ? event.output.split('\n').slice(0, TOOL_RESULT_MAX_DEFAULT_PREVIEW_LINES).join('\n')
    : '';

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
            {event.output.split('\n').length > TOOL_RESULT_MAX_DEFAULT_PREVIEW_LINES && ' ...'}
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

  if (tool === BASH_TOOL || tool === EXECUTE_TOOL || tool === RUN_COMMAND_TOOL) {
    return <BashResult event={event} theme={theme} />;
  }

  if (tool === FILE_WRITE_TOOL || tool === FILE_EDIT_TOOL || tool === FILE_DELETE_TOOL) {
    return <FileToolResult event={event} theme={theme} />;
  }

  if (tool === FILE_READ_TOOL) {
    const rawPath = String(event.metadata.path || event.metadata.filepath || '');
    const winPath = formatWindowsPath(rawPath);
    const readVerb = TOOL_VERB_LABELS[FILE_READ_TOOL];
    const readStatusColor = event.success ? theme.colors.status.success : theme.colors.status.error;
    const lines = event.output ? event.output.split('\n') : [];
    const isTruncated = lines.length > TOOL_RESULT_MAX_READ_PREVIEW_LINES;
    const visibleLines = isTruncated ? lines.slice(0, TOOL_RESULT_MAX_READ_PREVIEW_LINES) : lines;
    const gutterWidth = Math.max(2, String(lines.length).length);

    return (
      <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
        <Box flexDirection="row" alignItems="center">
          <Text color={readStatusColor} bold>
            ●{' '}
          </Text>
          <Text color={readStatusColor} bold>
            {readVerb}({winPath})
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
                ... [{lines.length - TOOL_RESULT_MAX_READ_PREVIEW_LINES} more lines]
              </Text>
            )}
          </Box>
        )}
      </Box>
    );
  }

  return <DefaultResult event={event} theme={theme} />;
});
