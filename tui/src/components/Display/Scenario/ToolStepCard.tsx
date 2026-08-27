import { Box, Text } from 'ink';
import React, { useRef } from 'react';
import { SPINNER_FRAMES } from '../../../constants/animation';
import {
  CANCELLED_ERROR_PATTERN,
  EXPLORE_TOOL,
  FILE_DELETE_TOOL_SET,
  FILE_MUTATION_TOOL_SET,
  FILE_READ_TOOL_SET,
  getToolStepPrimaryParam,
  getToolStepStatusText,
  getToolVerbLabel,
  LSP_TOOL_SET,
  SEARCH_TOOL_SET,
  SHELL_TOOL_SET,
  TOOL_META_INTERRUPTED,
  TOOL_META_REPEAT_COUNT,
} from '../../../constants/toolDisplay';
import { useAnimationTick } from '../../../context/AnimationContext';
import { useTheme } from '../../../theme/ThemeContext';
import type { ToolStepEvent } from '../../../types/scenario';
import { formatDuration } from '../../../utils/text';
import { getWorkspaceFolderName } from '../../../utils/workspacePath';
import type { EventRenderContext } from './componentRegistry';
import { formatErrorSummary } from './errorSummary';
import { buildUnifiedDiff, FileDiffBlock } from './FileDiffBlock';

/** Shape of the metadata payload the server attaches to explore results. */
interface ExploreMeta {
  agent_name?: string;
  agent_role?: string;
  thoroughness?: string;
  cached?: boolean;
  tokens_used?: number;
  tool_calls?: number;
  verified_count?: number;
  proposed_count?: number;
  unverified_count?: number;
  blocked_count?: number;
  affected_files?: string[];
}

function readExploreMeta(metadata: Record<string, unknown> | undefined): ExploreMeta {
  const m = metadata ?? {};
  const num = (key: string): number | undefined => {
    const v = m[key];
    return typeof v === 'number' && Number.isFinite(v) ? v : undefined;
  };
  return {
    agent_name: typeof m.agent_name === 'string' ? m.agent_name : undefined,
    agent_role: typeof m.agent_role === 'string' ? m.agent_role : undefined,
    thoroughness: typeof m.thoroughness === 'string' ? m.thoroughness : undefined,
    cached: m.cached === true,
    tokens_used: num('tokens_used'),
    tool_calls: num('tool_calls'),
    verified_count: num('verified_count'),
    proposed_count: num('proposed_count'),
    unverified_count: num('unverified_count'),
    blocked_count: num('blocked_count'),
    affected_files: Array.isArray(m.affected_files)
      ? (m.affected_files as unknown[]).filter((f): f is string => typeof f === 'string').slice(0, 6)
      : undefined,
  };
}

/**
 * WP5 crewmate card for `explore` missions: a modern, compact dossier for
 * the dispatched scout — identity header, live elapsed while flying, then
 * confidence chips + summary once the report lands.
 */
const ExploreCrewCard: React.FC<{
  event: ToolStepEvent;
  isPending: boolean;
  state: ExecutionState;
  elapsedMs: number;
  context?: EventRenderContext;
  metaPill: React.ReactNode;
  tick: number;
}> = React.memo(({ event, isPending, state, elapsedMs, tick }) => {
  const { theme } = useTheme();
  const meta = readExploreMeta(event.metadata);
  const agentName = meta.agent_name ?? 'Apogee';
  const agentRole = meta.agent_role ?? 'Codebase Explorer';
  const objective = collapseFirstLine(String(event.params.objective ?? ''));
  const ok = state === 'success';
  const summary =
    ok && !isPending
      ? stripAnsi(event.output || '')
          .replace(/^\[explore\][^\n]*\n?/, '')
          .trim()
      : '';

  const borderColor = isPending
    ? theme.colors.status.info
    : state === 'failed'
      ? theme.colors.status.error
      : state === 'cancelled'
        ? theme.colors.status.warning
        : theme.colors.border.muted;

  const durationSec =
    event.metadata?.duration_ms !== undefined
      ? Math.max(0, event.metadata.duration_ms as number)
      : isPending
        ? elapsedMs
        : 0;
  const durationText =
    durationSec > 0 || isPending ? formatDuration(Math.max(1000, Math.floor(durationSec / 1000) * 1000)) : '';

  /** Confidence chips: one glance = report trustworthiness. */
  const chips: { color: string; glyph: string; label: string }[] = [];
  if ((meta.verified_count ?? 0) > 0)
    chips.push({ color: theme.colors.status.success, glyph: '●', label: `${meta.verified_count} verified` });
  if ((meta.proposed_count ?? 0) > 0)
    chips.push({ color: theme.colors.status.warning, glyph: '●', label: `${meta.proposed_count} proposed` });
  if ((meta.unverified_count ?? 0) > 0)
    chips.push({ color: theme.colors.text.dim, glyph: '○', label: `${meta.unverified_count} unverified` });

  const statParts: string[] = [];
  if (typeof meta.tokens_used === 'number' && meta.tokens_used > 0)
    statParts.push(`${(meta.tokens_used / 1000).toFixed(1)}k tok`);
  if (typeof meta.tool_calls === 'number' && meta.tool_calls > 0) statParts.push(`${meta.tool_calls} calls`);

  return (
    <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
      <Box
        flexDirection="column"
        backgroundColor={theme.colors.code.background}
        borderStyle="round"
        borderColor={borderColor}
        paddingX={1}
        paddingY={0}
      >
        {/* Crewmate header: diamond sigil · name · role · thoroughness pill */}
        <Box flexDirection="row" alignItems="center" width="100%" flexWrap="nowrap">
          <Text
            color={isPending ? theme.colors.status.info : ok ? theme.colors.status.success : theme.colors.status.error}
            bold
          >
            ◆{' '}
          </Text>
          <Text color={theme.colors.text.bright} bold wrap="truncate-end">
            {agentName}
          </Text>
          <Text color={theme.colors.text.dim}> · {agentRole}</Text>
          <Box flexGrow={1} flexShrink={1} />
          {!isPending && meta.cached ? (
            <Box flexShrink={0} marginRight={1}>
              <Text color={theme.colors.status.warning}>↺ reused intelligence</Text>
            </Box>
          ) : null}
          <Box flexShrink={0}>
            <Text color={theme.colors.text.dim}>{meta.thoroughness ?? 'standard'}</Text>
          </Box>
          {durationText ? (
            <Box flexShrink={0} marginLeft={1}>
              <Text color={theme.colors.text.dim}>~ {durationText}</Text>
            </Box>
          ) : null}
        </Box>

        {/* Mission line: status glyph ❯ objective */}
        <Box flexDirection="row" alignItems="center">
          <Text
            color={isPending ? theme.colors.status.info : ok ? theme.colors.status.success : theme.colors.status.error}
            bold
          >
            {isPending
              ? `${SPINNER_FRAMES[tick % SPINNER_FRAMES.length]} `
              : ok
                ? '✓ '
                : state === 'cancelled'
                  ? '⊘ '
                  : '✗ '}
          </Text>
          <Text color={theme.colors.text.bright} wrap="truncate-end">
            {objective || 'Exploring…'}
          </Text>
        </Box>

        {/* Confidence chips row */}
        {!isPending && ok && chips.length > 0 ? (
          <Box flexDirection="row" paddingLeft={2} columnGap={2}>
            {chips.map((chip) => (
              <Text key={chip.label} color={chip.color}>
                {chip.glyph} {chip.label}
              </Text>
            ))}
            {statParts.length > 0 ? <Text color={theme.colors.text.dim}>{statParts.join(' · ')}</Text> : null}
          </Box>
        ) : null}

        {/* Report summary (capped excerpt of the structured findings text) */}
        {!isPending && ok && summary ? (
          <Box flexDirection="column" paddingLeft={2}>
            <Text color={theme.colors.code.output} wrap="truncate-end">
              {formatCommandOutput(summary, 4)}
            </Text>
          </Box>
        ) : null}

        {/* Affected files footer */}
        {!isPending && ok && meta.affected_files && meta.affected_files.length > 0 ? (
          <Box paddingLeft={2}>
            <Text color={theme.colors.text.dim} wrap="truncate-end">
              ⌲ {meta.affected_files.join(', ')}
            </Text>
          </Box>
        ) : null}

        {/* Failure context */}
        {!isPending && !ok && event.error ? (
          <Box paddingLeft={2}>
            <Text
              color={state === 'cancelled' ? theme.colors.status.warning : theme.colors.status.error}
              wrap="truncate-end"
            >
              {formatErrorSummary(event.error)}
            </Text>
          </Box>
        ) : null}
      </Box>
    </Box>
  );
});
ExploreCrewCard.displayName = 'ExploreCrewCard';

/** Cap on how many stdout lines are rendered inside the terminal window. */
const MAX_OUTPUT_LINES = 50;
/** Success output reads slightly deeper than failures (errors need less). */
const SHELL_OUTPUT_LINES_SUCCESS = 6;
const SHELL_OUTPUT_LINES_ERROR = 4;
/** Generic informational tools keep only a tiny excerpt. */
const GENERIC_OUTPUT_PREVIEW_LINES = 4;

/** Execution lifecycle glyphs — one visual language across every card. */
type ExecutionState = 'running' | 'success' | 'failed' | 'cancelled';

function resolveExecutionState(event: ToolStepEvent, isPending: boolean): ExecutionState {
  if (isPending) return 'running';
  if (event.success !== false) return 'success';
  const interruptedMeta = (event.metadata ?? {})[TOOL_META_INTERRUPTED] === true;
  if (interruptedMeta || CANCELLED_ERROR_PATTERN.test(event.error ?? '')) return 'cancelled';
  return 'failed';
}

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

interface ToolStepCardProps {
  event: ToolStepEvent;
  context?: EventRenderContext;
}

export const ToolStepCard: React.FC<ToolStepCardProps> = React.memo(({ event, context }) => {
  const { theme } = useTheme();
  const isPending = Boolean(event.pending && context?.isRunning && !context?.isHistorical);
  const tick = useAnimationTick();

  // Live elapsed time must measure from the tool step's own start, not from app
  // mount (the shared animation tick only re-renders; it is not a clock).
  const pendingStartRef = useRef<Map<string, number>>(new Map());
  const startedAt = isPending ? (pendingStartRef.current.get(event.id) ?? Date.now()) : undefined;
  if (isPending && startedAt !== undefined) {
    pendingStartRef.current.set(event.id, startedAt);
  } else {
    pendingStartRef.current.delete(event.id);
  }
  const elapsedMs = isPending && startedAt !== undefined ? Date.now() - startedAt : 0;

  const state = resolveExecutionState(event, isPending);
  const isSuccess = state === 'success';

  // Universal duration: server stamps metadata.duration_ms on every tool
  // result; while running we count wall-clock from the row's own mount.
  const metaDurMs =
    typeof event.metadata?.duration_ms === 'number' ? Math.max(0, event.metadata.duration_ms) : undefined;
  const durationSec = metaDurMs !== undefined ? metaDurMs : isPending ? elapsedMs : 0;
  const durationText =
    durationSec > 0 || isPending ? formatDuration(Math.max(1000, Math.floor(durationSec / 1000) * 1000)) : '';

  const repeatMeta = event.metadata?.[TOOL_META_REPEAT_COUNT];
  const repeatCount = typeof repeatMeta === 'number' && repeatMeta > 1 ? repeatMeta : 0;

  const primary = getToolStepPrimaryParam(event.tool, event.params);

  const statusText = !isPending ? getToolStepStatusText(event) : '';
  const verb = getToolVerbLabel(event.tool);
  const isGenericTemplate = event.text != null && /^Executing\s+.+(?:\.\.\.|…)$/.test(event.text.trim());
  const hasTextHeader = Boolean(event.text) && !isGenericTemplate;
  const headerText = (hasTextHeader ? event.text : `${verb}${primary ? ` ${primary.value}` : ''}`) || '';

  /** Status glyph column shared by every branch — one coherent language. */
  const statusGlyph = (() => {
    if (isPending) {
      return (
        <Text color={theme.colors.status.info} bold>
          {SPINNER_FRAMES[tick % SPINNER_FRAMES.length]}{' '}
        </Text>
      );
    }
    if (state === 'cancelled') {
      return (
        <Text color={theme.colors.status.warning} bold>
          ⊘{' '}
        </Text>
      );
    }
    return (
      <Text color={isSuccess ? theme.colors.status.success : theme.colors.status.error} bold>
        {isSuccess ? '✓' : '✗'}{' '}
      </Text>
    );
  })();

  /** Right-aligned meta pill: duration (+ repeat badge), used by all branches. */
  const metaPill = (
    <>
      {repeatCount > 0 ? (
        <Box flexShrink={0} marginLeft={1}>
          <Text color={theme.colors.text.dim}>×{repeatCount}</Text>
        </Box>
      ) : null}
      {durationText ? (
        <Box flexShrink={0} marginLeft={1}>
          <Text color={theme.colors.text.dim}>~ {durationText}</Text>
        </Box>
      ) : null}
    </>
  );

  const toolKey = event.tool.toLowerCase();
  const isShellCommand = SHELL_TOOL_SET.has(toolKey);
  const isGrepSearch = SEARCH_TOOL_SET.has(toolKey);
  const isFileRead = FILE_READ_TOOL_SET.has(toolKey);
  const isFileMutation = FILE_MUTATION_TOOL_SET.has(toolKey);

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
    if (
      ('file_edit' === lower || 'multi_edit' === lower || 'edit_file' === lower || 'replace_file_content' === lower) &&
      event.params
    ) {
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

  if (isShellCommand) {
    const meta = event.metadata ?? {};
    const exitCode = typeof meta.exit_code === 'number' ? meta.exit_code : undefined;

    // Border colour carries the execution state at a glance.
    const borderColor = isPending
      ? theme.colors.status.info
      : state === 'failed'
        ? theme.colors.status.error
        : state === 'cancelled'
          ? theme.colors.status.warning
          : theme.colors.border.muted;

    const promptLine = collapseFirstLine(cmdString);
    const folderName = getWorkspaceFolderName(context?.workspaceName);

    const cmdOutputText =
      event.output ||
      (typeof event.metadata?.output === 'string' ? event.metadata.output : '') ||
      (typeof event.metadata?.result === 'string' ? event.metadata.result : '') ||
      '';

    const trimInfo = event.metadata?.trim as { charsRemoved?: number } | undefined;
    return (
      <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
        <Box
          flexDirection="column"
          backgroundColor={theme.colors.code.background}
          borderStyle="round"
          borderColor={borderColor}
          paddingX={1}
          paddingY={0}
        >
          {/* Terminal Window Header Bar: Window Dots + Relative Folder:Branch + Duration */}
          <Box flexDirection="row" alignItems="center" width="100%" flexWrap="nowrap">
            <Box flexDirection="row" alignItems="center" flexGrow={1} flexShrink={1} overflow="hidden">
              <Text color={theme.colors.decorative.trafficLight.red}>● </Text>
              <Text color={theme.colors.decorative.trafficLight.yellow}>● </Text>
              <Text color={theme.colors.decorative.trafficLight.green}>● </Text>
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

            {metaPill}
          </Box>

          {/* Terminal Body Prompt Line: Status Icon ❯❯ Command String */}
          <Box flexDirection="row" alignItems="center">
            {statusGlyph}

            <Text color={theme.colors.text.bright} bold>
              ❯❯{' '}
            </Text>

            <Text color={theme.colors.text.bright} bold wrap="truncate-end">
              {promptLine || headerText}
            </Text>
          </Box>

          {/* Command execution response text on second line (height-truncated) */}
          {!isPending && cmdOutputText.trim().length > 0 ? (
            <Box flexDirection="column" paddingLeft={2} marginTop={0} marginBottom={0}>
              <Text color={theme.colors.code.output} wrap="truncate-end">
                {formatCommandOutput(cmdOutputText, isSuccess ? SHELL_OUTPUT_LINES_SUCCESS : SHELL_OUTPUT_LINES_ERROR)}
              </Text>
            </Box>
          ) : null}

          {/* Footer meta: failure context, exit code, model-side trim note */}
          {!isPending && !isSuccess && event.error ? (
            <Box paddingLeft={2}>
              <Text
                color={state === 'cancelled' ? theme.colors.status.warning : theme.colors.status.error}
                wrap="truncate-end"
              >
                {formatErrorSummary(event.error)}
              </Text>
            </Box>
          ) : null}
          {!isPending && typeof exitCode === 'number' && exitCode !== 0 ? (
            <Box paddingLeft={2}>
              <Text color={theme.colors.text.dim} wrap="truncate-end">
                · exit {exitCode}
              </Text>
            </Box>
          ) : null}
          {!isPending && trimInfo ? (
            <Box paddingLeft={2}>
              <Text color={theme.colors.text.dim} wrap="truncate-end">
                · trimmed {String(trimInfo.charsRemoved ?? '')} chars
              </Text>
            </Box>
          ) : null}
        </Box>
      </Box>
    );
  }

  /** WP5: dedicated crewmate card for explore missions. */
  if (toolKey === EXPLORE_TOOL) {
    return (
      <ExploreCrewCard
        event={event}
        isPending={isPending}
        state={state}
        elapsedMs={elapsedMs}
        context={context}
        metaPill={metaPill}
        tick={tick}
      />
    );
  }

  const isFileDelete = FILE_DELETE_TOOL_SET.has(toolKey);
  const isLsp = LSP_TOOL_SET.has(toolKey);

  const outputText =
    event.output ||
    (typeof event.metadata?.output === 'string' ? event.metadata.output : '') ||
    (typeof event.metadata?.content === 'string' ? event.metadata.content : '') ||
    (typeof event.metadata?.result === 'string' ? event.metadata.result : '') ||
    '';

  // Inline result counts keep read/search rows to ONE line total.
  const inlineCount = (() => {
    if (!isSuccess || isPending || outputText.trim().length === 0) return '';
    if (isFileRead) return `${outputText.split('\n').filter((l) => l.trim()).length} lines`;
    if (isGrepSearch) return `${outputText.split('\n').filter((l) => l.trim()).length} matches`;
    return '';
  })();

  return (
    <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
      {/* Tool Header Row */}
      <Box flexDirection="row" alignItems="center" width="100%" flexWrap="nowrap">
        {!isFileDelete ? statusGlyph : null}
        <Box flexGrow={1} flexShrink={1} overflow="hidden">
          {isFileDelete ? (
            <Text
              color={
                state === 'cancelled'
                  ? theme.colors.status.warning
                  : isSuccess
                    ? theme.colors.status.warning
                    : theme.colors.status.error
              }
              bold
              wrap="truncate-end"
            >
              {statusText || `${headerText} removed`}
            </Text>
          ) : isFileRead ? (
            <Text color={isSuccess ? theme.colors.status.info : theme.colors.text.bright} wrap="truncate-end">
              {hasTextHeader ? event.text : `Read ${primary?.value ?? (event.metadata?.path as string) ?? headerText}`}
              {inlineCount ? <Text color={theme.colors.text.dim}> · {inlineCount}</Text> : null}
            </Text>
          ) : isGrepSearch ? (
            <Text color={isSuccess ? theme.colors.status.info : theme.colors.text.bright} wrap="truncate-end">
              {hasTextHeader
                ? event.text
                : `${event.tool === 'glob' ? 'Glob' : 'Grep'} "${
                    primary?.value ?? (event.metadata?.pattern as string) ?? ''
                  }"`}
              {inlineCount ? <Text color={theme.colors.text.dim}> · {inlineCount}</Text> : null}
            </Text>
          ) : isLsp ? (
            <Text color={isSuccess ? theme.colors.status.info : theme.colors.text.bright} wrap="truncate-end">
              {verb} {primary?.value || ''}
            </Text>
          ) : (
            <Text
              color={
                state === 'cancelled'
                  ? theme.colors.status.warning
                  : isSuccess
                    ? theme.colors.text.bright
                    : theme.colors.status.error
              }
              bold={!isSuccess}
              wrap="truncate-end"
            >
              {!isSuccess
                ? statusText || `${headerText} failed`
                : hasTextHeader && event.tool !== 'get_tool_definition' && event.tool !== 'discover_capabilities'
                  ? headerText
                  : statusText}
            </Text>
          )}
        </Box>
        {metaPill}
      </Box>
      {/* Failure / cancellation context line */}
      {!isPending && !isSuccess && event.error ? (
        <Box paddingLeft={2}>
          <Text
            color={state === 'cancelled' ? theme.colors.status.warning : theme.colors.status.error}
            wrap="truncate-end"
          >
            {formatErrorSummary(event.error)}
          </Text>
        </Box>
      ) : null}
      {/* Unified Git Native Diff / Plain Code Box (file_write, file_edit, multi_edit) */}
      {isFileMutation && !isPending && isSuccess && diffOrContent ? (
        <FileDiffBlock diffOrContent={diffOrContent} title={primary?.value || undefined} />
      ) : null}
      {/* Non-shell informational tools keep a small capped output excerpt */}
      {!isFileMutation && !isPending && isSuccess && !isFileRead && !isGrepSearch && outputText.trim().length > 0 ? (
        <Box flexDirection="column" paddingLeft={2} marginTop={0}>
          <Text color={theme.colors.text.dim} wrap="truncate-end">
            {formatCommandOutput(outputText, GENERIC_OUTPUT_PREVIEW_LINES)}
          </Text>
        </Box>
      ) : null}
    </Box>
  );
});

ToolStepCard.displayName = 'ToolStepCard';
