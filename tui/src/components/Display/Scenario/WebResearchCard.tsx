import { Box, Text } from 'ink';
import React, { useRef } from 'react';
import { SPINNER_FRAMES } from '../../../constants/animation';
import { WEBFETCH_TOOL, WEBSEARCH_TOOL } from '../../../constants/toolDisplay';
import { useAnimationTick } from '../../../context/AnimationContext';
import { useTheme } from '../../../theme/ThemeContext';
import type { ToolStepEvent } from '../../../types/scenario';
import { formatDuration } from '../../../utils/text';
import type { EventRenderContext } from './componentRegistry';

/**
 * Web research dossier — medium of A2 (Detailed) + A3 (Modern).
 * Boxless, pill-shaded, typography hierarchy. Handles both websearch and
 * webfetch across running / success / failure + calm vs normal modes.
 */

function getDomain(url: string): string {
  try {
    const u = new URL(url);
    return u.hostname.replace(/^www\./, '');
  } catch {
    return url.split('/')[0] || url;
  }
}

function truncateMiddle(text: string, max: number): string {
  if (text.length <= max) return text;
  const half = Math.floor((max - 3) / 2);
  return `${text.slice(0, half)}…${text.slice(-half)}`;
}

function refTokenFromLine(line: string): string | null {
  const m = line.match(/\[ref:\s*([^\]]+)\]/i);
  return m ? m[1] : null;
}

function compact(n: number): string {
  if (n >= 1000) return `${Math.round(n / 1000)}k`;
  return String(n);
}

function truncatedCounts(output: string, totalChars?: number): { sliced?: number; total?: number } {
  const m = String(output).match(/truncated at ([\d,]+) chars?\b/i);
  const sliced = m ? Number(m[1].replace(/,/g, '')) : undefined;
  return { sliced, total: typeof totalChars === 'number' ? totalChars : undefined };
}

/** Spin only while pending — keeps completed/historical cards static. */
const LiveSpinner: React.FC<{ color: string }> = React.memo(({ color }) => {
  const tick = useAnimationTick();
  return (
    <Text color={color} bold>
      {SPINNER_FRAMES[tick % SPINNER_FRAMES.length]}{' '}
    </Text>
  );
});

LiveSpinner.displayName = 'LiveSpinner';

export const WebResearchCard: React.FC<{
  event: ToolStepEvent;
  context?: EventRenderContext;
}> = React.memo(({ event, context }) => {
  const { theme } = useTheme();
  const isPending = Boolean(event.pending && context?.isRunning && !context?.isHistorical);
  const isCalm = context?.calmMode === true;

  // Live elapsed must measure from the row's own mount, not the shared tick
  // (tick only re-renders; it is not a clock). Server duration_ms wins when done.
  const pendingStartRef = useRef<Map<string, number>>(new Map());
  const startedAt = isPending ? (pendingStartRef.current.get(event.id) ?? Date.now()) : undefined;
  if (isPending && startedAt !== undefined) pendingStartRef.current.set(event.id, startedAt);
  else pendingStartRef.current.delete(event.id);
  const liveMs = isPending && startedAt !== undefined ? Date.now() - startedAt : 0;
  const metaDurMs =
    typeof event.metadata?.duration_ms === 'number' ? Math.max(0, event.metadata.duration_ms) : undefined;
  const durationText =
    metaDurMs !== undefined || isPending
      ? formatDuration(Math.max(1000, Math.floor((metaDurMs ?? liveMs) / 1000) * 1000))
      : '';

  const isSearch = event.tool === WEBSEARCH_TOOL;
  const isFetch = event.tool === WEBFETCH_TOOL;
  const isFailed = !isPending && Boolean(event.error);
  const isSuccess = !isPending && !isFailed && event.success !== false;

  const query = String(
    event.params?.query ?? event.metadata?.query ?? (event.params?.queries as string[])?.[0] ?? '',
  );
  const queries = event.params?.queries as string[] | undefined;
  // metadata.url is the resolved target; params.url may be a ref_doc token.
  const url = String(event.metadata?.url || event.params?.url || '');
  const pattern = String(event.params?.pattern ?? '');
  const count = typeof event.metadata?.count === 'number' ? (event.metadata.count as number) : undefined;
  const totalLines =
    typeof event.metadata?.total_lines === 'number'
      ? (event.metadata.total_lines as number)
      : typeof event.metadata?.lines === 'number'
        ? (event.metadata.lines as number)
        : undefined;
  const matches = typeof event.metadata?.matches === 'number' ? (event.metadata.matches as number) : undefined;
  const source = String(event.metadata?.source ?? 'DuckDuckGo');
  const suggestions = String(event.metadata?.suggestions ?? '');

  const shade = theme.colors.code.background;
  const dim = theme.colors.text.dim;
  const bright = theme.colors.text.bright;
  const muted = theme.colors.text.muted;
  const info = theme.colors.status.info;
  const success = theme.colors.status.success;
  const warning = theme.colors.status.warning;
  const error = theme.colors.status.error;
  const accent = theme.colors.status.accent;

  const metaRow = (suffix: string) =>
    durationText ? (
      <Text color={dim}>
        {suffix ? '  ' : ''}{durationText}
      </Text>
    ) : null;

  // ── Failure (shared by search + fetch) ────────────────────────────────────
  if (isFailed) {
    const label = isSearch ? 'search' : 'fetch';
    const body = String(event.error || 'tool failed').replace(/\s+/g, ' ').trim();
    if (isCalm) {
      return (
        <Box flexDirection="column" width="100%" marginBottom={0} paddingX={1}>
          <Box flexDirection="row" alignItems="center">
            <Text color={dim} dimColor>
              · {label} ✗ — {truncateMiddle(body, 52)}
            </Text>
            {metaRow('')}
          </Box>
        </Box>
      );
    }
    return (
      <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
        <Box flexDirection="row" alignItems="center" width="100%" flexWrap="nowrap">
          <Text color={error} bold>
            ✗{' '}
          </Text>
          <Text color={error} bold>
            {label} failed
          </Text>
          <Text color={dim}> — </Text>
          <Box
            flexShrink={1}
            flexGrow={0}
            paddingX={1}
            backgroundColor={shade}
            overflow="hidden"
          >
            <Text color={muted} italic wrap="truncate-end">
              {truncateMiddle(body, 48)}
            </Text>
          </Box>
          <Box flexGrow={1} />
          {metaRow('')}
        </Box>
      </Box>
    );
  }

  // ── Search ────────────────────────────────────────────────────────────────
  if (isSearch) {
    if (isPending) {
      const q = query || (queries?.[0] ?? '');
      const allowed = event.params?.allowed_domains as string[] | undefined;
      if (isCalm) {
        return (
          <Box flexDirection="column" width="100%" marginBottom={0} paddingX={1}>
            <Box flexDirection="row" alignItems="center">
              <Text color={dim} dimColor>
                · search  "{truncateMiddle(q, 44)}"
              </Text>
              {metaRow('')}
            </Box>
          </Box>
        );
      }
      return (
        <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
          <Box flexDirection="row" alignItems="center">
            <LiveSpinner color={info} />
            <Text color={dim}>Searching</Text>
            <Box
              marginLeft={1}
              paddingX={1}
              backgroundColor={shade}
              overflow="hidden"
            >
              <Text color={bright} bold wrap="truncate-end">
                "{truncateMiddle(q, 44)}"
              </Text>
            </Box>
            {allowed?.[0] ? (
              <Box marginLeft={1} paddingX={1} backgroundColor={shade}>
                <Text color={accent} bold>
                  {allowed[0]}
                </Text>
              </Box>
            ) : null}
            <Box flexGrow={1} />
            {metaRow('')}
          </Box>
          {source || count !== undefined ? (
            <Box paddingLeft={2} marginTop={0}>
              <Text color={dim} dimColor>
                {count ?? '—'} · {source}
              </Text>
            </Box>
          ) : null}
        </Box>
      );
    }

    // No results — surface the server-provided suggestion when present.
    if (count === 0) {
      const hint = suggestions || 'no results — try a broader query';
      if (isCalm) {
        return (
          <Box flexDirection="column" width="100%" marginBottom={0} paddingX={1}>
            <Box flexDirection="row" alignItems="center">
              <Text color={dim} dimColor>
                · no results — "{truncateMiddle(query, 36)}"
              </Text>
              {metaRow('')}
            </Box>
          </Box>
        );
      }
      return (
        <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
          <Box flexDirection="row" alignItems="center">
            <Text color={warning} bold>
              ○{' '}
            </Text>
            <Text color={warning}>no results</Text>
            <Text color={dim}> — "{truncateMiddle(query, 36)}"</Text>
            <Box flexGrow={1} />
            {metaRow('')}
          </Box>
          <Box paddingLeft={2} marginTop={0}>
            <Text color={dim} dimColor italic wrap="truncate-end">
              {truncateMiddle(hint, 64)}
            </Text>
          </Box>
        </Box>
      );
    }

    const displayQuery = query || (queries?.[0] ?? '');
    const multi = Array.isArray(queries) && queries.length > 1;
    const previewLines = String(event.output || '')
      .split('\n')
      .map((l) => l.trim())
      .filter((l) => /^\d+\. /.test(l))
      .slice(0, 2);
    const firstRef = String(event.output || '')
      .split('\n')
      .map((l) => refTokenFromLine(l))
      .find((t) => t !== null);

    if (isCalm) {
      return (
        <Box flexDirection="column" width="100%" marginBottom={0} paddingX={1}>
          <Box flexDirection="row" alignItems="center" width="100%" flexWrap="nowrap">
            <Text color={dim} dimColor>
              · {count ?? ''} · {source} — "{truncateMiddle(displayQuery, 38)}"
            </Text>
            <Box flexGrow={1} />
            {metaRow('')}
          </Box>
        </Box>
      );
    }
    return (
      <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
        <Box flexDirection="row" alignItems="center" width="100%" flexWrap="nowrap">
          <Text color={isSuccess ? success : dim} bold>
            {isSuccess ? '●' : '○'}{' '}
          </Text>
          <Text color={dim}>Found</Text>
          <Box marginX={1} paddingX={1} backgroundColor={shade}>
            <Text color={isSuccess ? success : dim} bold>
              {count ?? ''} 
            </Text>
          </Box>
          <Text color={dim}>·</Text>
          <Text color={info} bold>
            {' ' + source}
          </Text>
          <Box marginLeft={1} paddingX={1} backgroundColor={shade} overflow="hidden">
            <Text color={bright} italic wrap="truncate-end">
              "{truncateMiddle(displayQuery, 30)}"
            </Text>
          </Box>
          {multi ? (
            <Box marginLeft={1} paddingX={1} backgroundColor={shade}>
              <Text color={muted} bold>
                +{queries.length - 1}
              </Text>
            </Box>
          ) : null}
          <Box flexGrow={1} />
          {metaRow('')}
        </Box>
        {isSuccess && previewLines.length > 0 ? (
          <Box flexDirection="column" paddingLeft={2} marginTop={0}>
            {previewLines.map((line, i) => {
              const ref = refTokenFromLine(line);
              return (
                <Box key={i} flexDirection="row" alignItems="center" overflow="hidden">
                  <Text color={muted} wrap="truncate-end">
                    {truncateMiddle(line, 60)}
                  </Text>
                  {ref ? (
                    <Box marginLeft={1} paddingX={1} backgroundColor={shade}>
                      <Text color={accent} bold>
                        {ref}
                      </Text>
                    </Box>
                  ) : null}
                </Box>
              );
            })}
            {count !== undefined && count > 2 ? (
              <Text color={dim} dimColor>
                +{count - 2} more{firstRef ? ` · Next → webfetch ${firstRef}` : ' · use webfetch for details'}
              </Text>
            ) : null}
          </Box>
        ) : null}
      </Box>
    );
  }

  // ── Fetch ─────────────────────────────────────────────────────────────────
  if (isFetch) {
    if (isPending) {
      const pat = pattern ? `"${truncateMiddle(pattern, 22)}"` : '';
      const dom = url ? getDomain(url) : '';
      if (isCalm) {
        return (
          <Box flexDirection="column" width="100%" marginBottom={0} paddingX={1}>
            <Box flexDirection="row" alignItems="center">
              <Text color={dim} dimColor>
                · fetch {pat ? pat + ' · ' : ''}{dom || truncateMiddle(url, 28)}
              </Text>
              {metaRow('')}
            </Box>
          </Box>
        );
      }
      return (
        <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
          <Box flexDirection="row" alignItems="center">
            <LiveSpinner color={info} />
            <Text color={dim}>Fetching</Text>
            {dom ? (
              <Box marginLeft={1} paddingX={1} backgroundColor={shade}>
                <Text color={info} bold>
                  {dom}
                </Text>
              </Box>
            ) : null}
            {pat ? (
              <Box marginLeft={1} paddingX={1} backgroundColor={shade} overflow="hidden">
                <Text color={bright} italic wrap="truncate-end">
                  {pat}
                </Text>
              </Box>
            ) : null}
            <Box flexGrow={1} />
            {metaRow('')}
          </Box>
        </Box>
      );
    }

    // Pattern / find-in-page mode
    if (pattern) {
      const m = matches ?? 0;
      const tl = totalLines ?? 0;
      if (m === 0) {
        const hint = suggestions || 'try a shorter keyword · read sections via start_line/end_line';
        if (isCalm) {
          return (
            <Box flexDirection="column" width="100%" marginBottom={0} paddingX={1}>
              <Box flexDirection="row" alignItems="center">
                <Text color={dim} dimColor>
                  · no matches "{pattern}" · {tl} lines
                </Text>
                {metaRow('')}
              </Box>
            </Box>
          );
        }
        return (
          <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
            <Box flexDirection="row" alignItems="center">
              <Text color={warning} bold>
                ○{' '}
              </Text>
              <Text color={dim}>no matches</Text>
              <Box marginLeft={1} paddingX={1} backgroundColor={shade}>
                <Text color={bright} bold wrap="truncate-end">
                  "{truncateMiddle(pattern, 24)}"
                </Text>
              </Box>
              <Text color={dim}> · {tl} lines</Text>
              <Box flexGrow={1} />
              {metaRow('')}
            </Box>
            <Box paddingLeft={2} marginTop={0}>
              <Text color={dim} dimColor italic wrap="truncate-end">
                {truncateMiddle(hint, 64)}
              </Text>
            </Box>
          </Box>
        );
      }
      const shown = typeof event.metadata?.shown === 'number' ? (event.metadata.shown as number) : undefined;
      const pills = String(event.output || '')
        .split('\n')
        .filter((l) => l.trim().startsWith('>>>'))
        .slice(0, 2)
        .map((l) => l.trim().replace(/^>>>\s*/, ''));
      const tail = shown !== undefined && shown < m ? ` · first ${shown}` : '';
      if (isCalm) {
        return (
          <Box flexDirection="column" width="100%" marginBottom={0} paddingX={1}>
            <Box flexDirection="row" alignItems="center">
              <Text color={dim} dimColor>
                · {m} matches · {tl} lines — "{truncateMiddle(pattern, 20)}"{tail}
              </Text>
              {metaRow('')}
            </Box>
          </Box>
        );
      }
      return (
        <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
          <Box flexDirection="row" alignItems="center">
            <Box paddingX={1} backgroundColor={shade}>
              <Text color={warning} bold>
                ◆ {m}
              </Text>
            </Box>
            <Text color={dim}> matches</Text>
            <Text color={dim}> · {tl} lines —</Text>
            <Box marginLeft={1} paddingX={1} backgroundColor={shade} overflow="hidden">
              <Text color={bright} italic bold wrap="truncate-end">
                "{truncateMiddle(pattern, 18)}"
              </Text>
            </Box>
            {tail ? (
              <Text color={dim} dimColor>
                {' ' + tail}
              </Text>
            ) : null}
            <Box flexGrow={1} />
            {metaRow('')}
          </Box>
          {pills.length > 0 ? (
            <Box flexDirection="column" paddingLeft={2} marginTop={0}>
              {pills.map((p, i) => (
                <Box key={i} paddingX={1} backgroundColor={i === 0 ? warning + '20' : shade} overflow="hidden">
                  <Text color={i === 0 ? warning : muted} bold={i === 0} wrap="truncate-end">
                    {truncateMiddle(p, 64)}
                  </Text>
                </Box>
              ))}
            </Box>
          ) : null}
        </Box>
      );
    }

    // Full document / line-range fetch
    const isRange = Boolean(event.params?.start_line !== undefined || event.params?.end_line !== undefined);
    const startLine = event.params?.start_line !== undefined ? Number(event.params.start_line) : undefined;
    const endLine = event.params?.end_line !== undefined ? Number(event.params.end_line) : undefined;
    const chars = typeof event.metadata?.chars === 'number' ? (event.metadata.chars as number) : undefined;
    const { sliced } = truncatedCounts(event.output || '', chars);
    const truncated = event.metadata?.truncated === true;
    const truncLabel = isRange
      ? `lines ${startLine ?? 1}${endLine ? '–' + endLine : '+'}`
      : truncated
        ? sliced !== undefined && chars !== undefined
          ? `truncated ${compact(sliced)}/${compact(chars)} → start_line`
          : 'truncated → start_line'
        : '';
    if (isCalm) {
      return (
        <Box flexDirection="column" width="100%" marginBottom={0} paddingX={1}>
          <Box flexDirection="row" alignItems="center">
            <Text color={dim} dimColor>
              · fetch {url ? getDomain(url) : 'page'}
              {totalLines ? ` · ${totalLines} lines` : ''}
              {truncLabel ? ` — ${truncLabel}` : ''}
            </Text>
            {metaRow('')}
          </Box>
        </Box>
      );
    }
    return (
      <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
        <Box flexDirection="row" alignItems="center">
          <Text color={isSuccess ? success : dim} bold>
            {isSuccess ? '●' : '○'}{' '}
          </Text>
          <Text color={dim}>fetch</Text>
          <Box marginLeft={1} paddingX={1} backgroundColor={shade}>
            <Text color={info} bold>
              {url ? getDomain(url) : 'page'}
            </Text>
          </Box>
          {totalLines ? <Text color={dim}> · {totalLines} lines</Text> : null}
          {truncLabel ? (
            <Box marginLeft={1} paddingX={1} backgroundColor={warning + '20'}>
              <Text color={warning} bold>
                {truncLabel}
              </Text>
            </Box>
          ) : null}
          <Box flexGrow={1} />
          {metaRow('')}
        </Box>
        {url && !truncated ? (
          <Box paddingLeft={2}>
            <Text color={dim} dimColor italic wrap="truncate-end">
              {truncateMiddle(url, 68)}
            </Text>
          </Box>
        ) : null}
      </Box>
    );
  }

  return null;
});

WebResearchCard.displayName = 'WebResearchCard';