import { Box, Text } from 'ink';
import React from 'react';
import { SPINNER_FRAMES } from '../../../constants/animation';
import { getToolStepPrimaryParam, getToolStepStatusText, getToolVerbLabel } from '../../../constants/toolDisplay';
import { useAnimationTick } from '../../../context/AnimationContext';
import { useTheme } from '../../../theme/ThemeContext';
import type { ToolStepEvent } from '../../../types/scenario';
import { formatDuration } from '../../../utils/text';
import { getWorkspaceFolderName } from '../../../utils/workspacePath';
import type { EventRenderContext } from './componentRegistry';
import { buildUnifiedDiff, FileDiffBlock } from './FileDiffBlock';

/** Cap on how many stdout lines are rendered inside the terminal window. */
const MAX_OUTPUT_LINES = 50;
const MAX_FAILED_OUTPUT_LINES = 20;
const MAX_TAB_NAME_LENGTH = 60;

/** Strip ANSI escape sequences from command output strings to prevent Ink rendering glitches. */
function stripAnsi(text: string): string {
  return text.replace(/[\u001b\u009b][[()#;?]*(?:[0-9]{1,4}(?:;[0-9]{0,4})*)?[0-9A-ORZcf-nqry=><]/g, '');
}

/** Format raw command output: strip ANSI codes, boilerplate headers, normalize line endings, trim trailing blanks, and cap to size. */
function formatCommandOutput(output: string, maxLines = MAX_OUTPUT_LINES): string {
  const sanitized = stripAnsi(output)
    .replace(/\r\n/g, '\n')
    .replace(/\r/g, '\n')
    .split('\n')
    .filter((line) => !/^\[Tool:\s*[^\]]+\|\s*Status:\s*[^\]]+\]/i.test(line.trim()))
    .join('\n')
    .replace(/\s+$/, '');
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
  const isFileMutation = [
    'file_write',
    'write_file',
    'edit_file',
    'create_file',
    'file_edit',
    'multi_edit',
  ].includes(event.tool.toLowerCase());

  const cmdString = primary?.value ?? (event.params.command as string) ?? '';

  // Resolve the diff/content to render underneath the header. Prefer a
  // server-captured unified diff (params.diff or metadata.diff), then raw file
  // content for brand-new files, and finally build a hunk-only diff on the
  // client for legacy file_edit events that carry no server-side diff.
  const diffOrContent = (() => {
    const fromParams =
      (event.params.diff as string) ||
      (event.params.content as string) ||
      (event.params.code as string) ||
      (event.params.patch as string) ||
      '';
    if (fromParams) return fromParams;
    if (typeof event.metadata?.diff === 'string' && event.metadata.diff) return event.metadata.diff;
    const lower = event.tool.toLowerCase();
    if (('file_edit' === lower || 'multi_edit' === lower || 'edit_file' === lower || 'replace_file_content' === lower) && event.params) {
      const oldContent =
        (event.params.old_content as string) ??
        (event.params.target_content as string) ??
        (event.params.TargetContent as string) ??
        '';
      const newContent =
        (event.params.new_content as string) ??
        (event.params.replacement_content as string) ??
        (event.params.ReplacementContent as string) ??
        '';
      if (oldContent || newContent) return buildUnifiedDiff(oldContent, newContent);
    }
    return '';
  })();

  const isSuccess = event.success !== false;

  if (isShellCommand) {
    const meta = event.metadata ?? {};
    const durMs = typeof meta.duration_ms === 'number' ? meta.duration_ms : undefined;
    const durSec = durMs !== undefined ? Math.max(1, Math.floor(durMs / 1000)) : isPending ? Math.max(1, Math.floor(elapsed / 10)) : 0;
    const duration = durSec > 0 ? formatDuration(durSec * 1000) : '';

    const promptLine = collapseFirstLine(cmdString);
    const folderName = getWorkspaceFolderName(context?.workspaceName);

    const cmdOutputText =
      event.output ||
      (typeof event.metadata?.output === 'string' ? event.metadata.output : '') ||
      (typeof event.metadata?.result === 'string' ? event.metadata.result : '') ||
      '';

    return (
      <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
        <Box
          flexDirection="column"
          backgroundColor={theme.colors.code.background}
          borderStyle="round"
          borderColor={theme.colors.border.muted}
          paddingX={1}
          paddingY={0}
        >
          {/* Terminal Window Header Bar: Window Dots + Relative Folder:Branch + Duration */}
          <Box flexDirection="row" alignItems="center" width="100%" flexWrap="nowrap">
            <Box flexDirection="row" alignItems="center" flexGrow={1} flexShrink={1} overflow="hidden">
              <Text color="#FF5F56">● </Text>
              <Text color="#FFBD2E">● </Text>
              <Text color="#27C93F">● </Text>
              <Text color={theme.colors.status.info} bold wrap="truncate-end">
                {folderName}
              </Text>
              {context?.gitBranch ? (
                <>
                  <Text color={theme.colors.text.dim}>:</Text>
                  <Text color={theme.colors.status.warning} wrap="truncate-end">
                    {context.gitBranch}
                  </Text>
                </>
              ) : null}
            </Box>

            {duration ? (
              <Box flexGrow={0} flexShrink={0} marginLeft={1}>
                <Text color={theme.colors.text.dim}>~ {duration}</Text>
              </Box>
            ) : null}
          </Box>

          {/* Terminal Body Prompt Line: Status Icon ❯❯ Command String */}
          <Box flexDirection="row" alignItems="center">
            {isPending ? (
              <Text color={theme.colors.status.info} bold>
                {SPINNER_FRAMES[tick % SPINNER_FRAMES.length]}{' '}
              </Text>
            ) : (
              <Text color={isSuccess ? theme.colors.status.success : theme.colors.status.error} bold>
                {isSuccess ? '✓ ' : '✗ '}
              </Text>
            )}

            <Text color={theme.colors.text.bright} bold>
              ❯❯{' '}
            </Text>

            <Text color={theme.colors.text.bright} bold wrap="truncate-end">
              {promptLine || headerText}
            </Text>
          </Box>

          {/* Failure Error Context */}
          {!isPending && !isSuccess && event.error ? (
            <Box flexDirection="column" paddingLeft={2} marginTop={0}>
              <Text color={theme.colors.status.error} wrap="truncate-end">
                └─ Error: {event.error}
              </Text>
            </Box>
          ) : null}

          {/* Command execution response text on second line (height-truncated) */}
          {!isPending && cmdOutputText.trim().length > 0 ? (
            <Box flexDirection="column" paddingLeft={2} marginTop={0} marginBottom={0}>
              <Text color={theme.colors.code.output} wrap="truncate-end">
                {formatCommandOutput(cmdOutputText, isSuccess ? 6 : 4)}
              </Text>
            </Box>
          ) : null}
        </Box>
      </Box>
    );
  }

  const isFileDelete = ['file_delete', 'delete_file'].includes(event.tool.toLowerCase());
  const isLsp = ['lsp_definition', 'lsp_diagnostics', 'lsp_rename'].includes(event.tool.toLowerCase());

  const outputText =
    event.output ||
    (typeof event.metadata?.output === 'string' ? event.metadata.output : '') ||
    (typeof event.metadata?.content === 'string' ? event.metadata.content : '') ||
    (typeof event.metadata?.result === 'string' ? event.metadata.result : '') ||
    '';

  return (
    <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
      {/* Tool Header Row */}
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
        ) : isFileDelete ? (
          <Text color={isSuccess ? theme.colors.status.warning : theme.colors.status.error} bold>
            {statusText}
          </Text>
        ) : isFileRead ? (
          <Text color={isSuccess ? theme.colors.status.info : theme.colors.status.error}>
            {isSuccess ? '✓' : '✗'} Read {primary?.value || headerText}
          </Text>
        ) : isGrepSearch ? (
          <Text color={isSuccess ? theme.colors.status.warning : theme.colors.status.error}>
            {isSuccess ? '✓' : '✗'} {event.tool === 'glob' ? 'Glob' : 'Grep'} &quot;{primary?.value || ''}&quot;
          </Text>
        ) : isLsp ? (
          <Text color={isSuccess ? theme.colors.status.info : theme.colors.status.error}>
            {isSuccess ? '✓' : '✗'} {verb} {primary?.value || ''}
          </Text>
        ) : (
          <Text color={isSuccess ? theme.colors.status.success : theme.colors.status.error} bold>
            {!isSuccess
              ? statusText || `✗ ${headerText} failed`
              : hasTextHeader && event.tool !== 'get_tool_definition' && event.tool !== 'discover_capabilities'
                ? headerText
                : statusText}
          </Text>
        )}
      </Box>

      {/* Failure Error Context Box */}
      {!isPending && !isSuccess && event.error ? (
        <Box
          flexDirection="column"
          paddingLeft={2}
          marginTop={0}
          marginBottom={0}
        >
          <Text color={theme.colors.status.error} wrap="truncate-end">
            └─ Error: {event.error}
          </Text>
        </Box>
      ) : null}

      {/* Unified Git Native Diff / Plain Code Box (file_write, file_edit, multi_edit) */}
      {isFileMutation && !isPending && isSuccess && diffOrContent ? (
        <FileDiffBlock diffOrContent={diffOrContent} title={primary?.value || undefined} />
      ) : null}

      {/* Truncated Minimized Output Snippet (for read / grep / glob / lsp / command outputs) */}
      {!isFileMutation && !isPending && isSuccess && outputText.trim().length > 0 ? (
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
