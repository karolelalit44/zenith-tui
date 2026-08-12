import { Box, Text } from 'ink';
import React from 'react';
import { SPINNER_FRAMES } from '../../../constants/animation';
import { getToolStepPrimaryParam, getToolStepStatusText, getToolVerbLabel } from '../../../constants/toolDisplay';
import { useAnimationTick } from '../../../context/AnimationContext';
import { useTheme } from '../../../theme/ThemeContext';
import type { ToolStepEvent } from '../../../types/scenario';
import type { EventRenderContext } from './componentRegistry';
import { FileDiffBlock } from './FileDiffBlock';

/** Cap on how many stdout lines are rendered inside the terminal window. */
const MAX_OUTPUT_LINES = 50;
const MAX_FAILED_OUTPUT_LINES = 20;
const MAX_TAB_NAME_LENGTH = 60;

/** Strip ANSI escape sequences from command output strings to prevent Ink rendering glitches. */
function stripAnsi(text: string): string {
  return text.replace(/[\u001b\u009b][[()#;?]*(?:[0-9]{1,4}(?:;[0-9]{0,4})*)?[0-9A-ORZcf-nqry=><]/g, '');
}

/** Format raw command output: strip ANSI codes, normalize line endings, trim trailing blanks, and cap to size. */
function formatCommandOutput(output: string, maxLines = MAX_OUTPUT_LINES): string {
  const sanitized = stripAnsi(output).replace(/\r\n/g, '\n').replace(/\r/g, '\n').replace(/\s+$/, '');
  const lines = sanitized.split('\n');
  if (lines.length <= maxLines) return sanitized;
  const kept = lines.slice(0, maxLines).join('\n');
  return `${kept}\n… ${lines.length - maxLines} more lines`;
}

/** Collapse a multi-line command to its first line, signalling truncation. */
function collapseFirstLine(text: string): string {
  const line = text.split('\n')[0].trim();
  return text.includes('\n') ? `${line} …` : line;
}

/** Hard-truncate a single-line label with an ellipsis. */
function truncateLabel(text: string, max: number): string {
  return text.length > max ? `${text.slice(0, max - 1).trimEnd()}…` : text;
}

interface ToolStepCardProps {
  event: ToolStepEvent;
  context?: EventRenderContext;
}

export const ToolStepCard: React.FC<ToolStepCardProps> = React.memo(({ event, context }) => {
  const { theme } = useTheme();
  const isPending = event.pending && context?.isRunning && !context?.isHistorical;
  const tick = useAnimationTick();
  const elapsed = isPending ? tick : 0;

  const primary = getToolStepPrimaryParam(event.tool, event.params);

  const statusText = !isPending ? getToolStepStatusText(event) : '';
  const verb = getToolVerbLabel(event.tool);
  const isGenericTemplate = event.text != null && /^Executing\s+.+(?:\.\.\.|…)$/.test(event.text.trim());
  const hasTextHeader = Boolean(event.text) && !isGenericTemplate;
  const headerText = (hasTextHeader ? event.text : `${verb}${primary ? ` ${primary.value}` : ''}`) || '';

  const isShellCommand = ['bash', 'run_command', 'execute'].includes(event.tool.toLowerCase());
  const isGrepSearch = ['grep', 'grep_search', 'glob'].includes(event.tool.toLowerCase());
  const isFileRead = ['file_read', 'read_file'].includes(event.tool.toLowerCase());
  const isFileWrite = ['file_write', 'write_file', 'edit_file', 'create_file'].includes(event.tool.toLowerCase());

  const cmdString = primary?.value ?? (event.params.command as string) ?? '';
  const diffOrContent =
    (event.params.diff as string) ||
    (event.params.content as string) ||
    (event.params.code as string) ||
    (event.params.patch as string) ||
    '';

  const isSuccess = event.success !== false;

  if (isShellCommand) {
    const meta = event.metadata ?? {};
    const durMs = typeof meta.duration_ms === 'number' ? meta.duration_ms : undefined;
    const duration = durMs !== undefined ? `${(durMs / 1000).toFixed(1)}s` : '';

    const tabName = truncateLabel(cmdString.split('\n')[0].trim(), MAX_TAB_NAME_LENGTH);
    const promptLine = collapseFirstLine(cmdString);
    const cwdBase = context?.workspaceName?.replace(/\\/g, '/').split('/').filter(Boolean).pop();
    const pathText = cwdBase ? `~/${cwdBase}` : '';

    return (
      <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
        <Box
          flexDirection="column"
          backgroundColor={theme.colors.code.background}
          borderStyle="single"
          borderColor={theme.colors.border.muted}
          paddingX={1}
          paddingY={0}
        >
          {/* Header bar: TERMINAL · path · branch + timing */}
          <Box flexDirection="row" alignItems="center" width="100%" flexWrap="nowrap">
            <Box flexDirection="row" alignItems="center" flexGrow={1} flexShrink={1} overflow="hidden">
              <Text color={theme.colors.text.bright} bold wrap="truncate-end">
                TERMINAL
              </Text>
              {pathText ? (
                <>
                  <Text color={theme.colors.text.dim} wrap="truncate-end"> · </Text>
                  <Text color={theme.colors.status.info} wrap="truncate-end">{pathText}</Text>
                </>
              ) : null}
              {context?.gitBranch ? (
                <>
                  <Text color={theme.colors.text.dim} wrap="truncate-end"> · </Text>
                  <Text color={theme.colors.status.warning} wrap="truncate-end">⚡ {context.gitBranch}</Text>
                </>
              ) : null}
              {tabName ? (
                <>
                  <Text color={theme.colors.text.dim} wrap="truncate-end"> · </Text>
                  <Text color={theme.colors.text.muted} wrap="truncate-end">
                    {tabName}
                  </Text>
                </>
              ) : null}
            </Box>
            {duration ? (
              <Box flexGrow={0} flexShrink={0} marginLeft={1}>
                <Text color={theme.colors.text.dim} wrap="truncate-end">~ took {duration}</Text>
              </Box>
            ) : null}
          </Box>

          {/* Prompt line */}
          <Box flexDirection="row" alignItems="center">
            {isPending ? (
              <Text color={theme.colors.status.info} bold>
                {SPINNER_FRAMES[tick % SPINNER_FRAMES.length]}{' '}
              </Text>
            ) : (
              <Text color={isSuccess ? theme.colors.status.success : theme.colors.status.error} bold>
                ❯{' '}
              </Text>
            )}
            <Text color={theme.colors.text.bright} bold wrap="truncate-end">
              {promptLine || headerText}
            </Text>
            {isPending && <Text color={theme.colors.text.muted}> ({(elapsed / 10).toFixed(0)}s)</Text>}
          </Box>

          {/* Failure reason */}
          {!isPending && !isSuccess && event.error ? (
            <Box flexDirection="row" width="100%">
              <Box flexGrow={1} flexShrink={1}>
                <Text color={theme.colors.status.error} bold wrap="wrap">
                  {event.error}
                </Text>
              </Box>
            </Box>
          ) : null}

          {/* Execution output */}
          {!isPending && event.output && event.output.trim().length > 0 ? (
            <Box flexDirection="column" backgroundColor={theme.colors.code.background} paddingX={0} paddingY={0}>
              <Text color={theme.colors.code.output} wrap="wrap">
                {formatCommandOutput(event.output, isSuccess ? MAX_OUTPUT_LINES : MAX_FAILED_OUTPUT_LINES)}
              </Text>
            </Box>
          ) : null}

          {/* Execution status footer inside padding */}
          {!isPending ? (
            <Box flexDirection="row" justifyContent="flex-end" width="100%">
              <Text color={isSuccess ? theme.colors.status.success : theme.colors.status.error}>
                {isSuccess ? '✓' : '✗'} Ran command{duration ? ` (${duration})` : ''}
              </Text>
            </Box>
          ) : null}
        </Box>
      </Box>
    );
  }

  const outputText =
    event.output ||
    (typeof event.metadata?.output === 'string' ? event.metadata.output : '') ||
    (typeof event.metadata?.content === 'string' ? event.metadata.content : '') ||
    (typeof event.metadata?.result === 'string' ? event.metadata.result : '') ||
    '';

  return (
    <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
      <Box flexDirection="row" alignItems="center">
        {isPending ? (
          <>
            <Text color={theme.colors.status.info} bold>
              {SPINNER_FRAMES[tick % SPINNER_FRAMES.length]}{' '}
            </Text>
            <Text color={theme.colors.text.bright} bold>
              {headerText}
            </Text>
            <Text color={theme.colors.text.muted}> ({(elapsed / 10).toFixed(0)}s)</Text>
          </>
        ) : isFileRead ? (
          <Text color={isSuccess ? theme.colors.status.info : theme.colors.status.error}>
            {isSuccess ? '✓' : '✗'} Read {primary?.value || headerText}
          </Text>
        ) : isGrepSearch ? (
          <Text color={isSuccess ? theme.colors.status.warning : theme.colors.status.error}>
            {isSuccess ? '✓' : '✗'} {event.tool === 'glob' ? 'Glob' : 'Grep'} &quot;{primary?.value || ''}&quot;
          </Text>
        ) : (
          <Text color={isSuccess ? theme.colors.status.success : theme.colors.status.error} bold>
            {event.tool === 'get_tool_definition'
              ? statusText
              : !isSuccess
                ? statusText || `✗ ${headerText} failed${event.error ? `: ${event.error}` : ''}`
                : `● ${headerText}`}
          </Text>
        )}
      </Box>

      {/* File Diff / Patch Box (for file_write) */}
      {isFileWrite && !isPending && diffOrContent ? (
        <FileDiffBlock diffOrContent={diffOrContent} />
      ) : null}

      {/* Truncated / Minimized Output Snippet (for read / grep / glob / commands) */}
      {!isFileWrite && !isPending && outputText.trim().length > 0 ? (
        <Box flexDirection="column" paddingLeft={2} marginTop={0}>
          <Text color={theme.colors.text.dim} wrap="truncate-end">
            {formatCommandOutput(outputText, 4)}
          </Text>
        </Box>
      ) : null}
    </Box>
  );
});

ToolStepCard.displayName = 'ToolStepCard';
