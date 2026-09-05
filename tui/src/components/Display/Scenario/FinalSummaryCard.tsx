import { Box, Text } from 'ink';
import React from 'react';
import { useTheme } from '../../../theme/ThemeContext';
import type { SessionSummarizedEvent } from '../../../types/scenario';

interface FinalSummaryCardProps {
  event: SessionSummarizedEvent;
}

interface Row {
  label: string;
  values: string[];
  accent: string;
}

const MAX_ROWS_PER_SECTION = 5;

/**
 * End-of-run summary card rendered from the backend's authoritative
 * SessionRunState snapshot (`session_summarized`). Every row is evidence-derived:
 * outcome ← status/final, discovered ← findings, changed ← manifest.created,
 * affected ← manifest.modified, verification ← manifest.completed/stalled,
 * unresolved ← terminal outcome when the run did not complete, next ← remaining
 * todos. Sections with no data render nothing — prose is never fabricated.
 */
export const FinalSummaryCard: React.FC<FinalSummaryCardProps> = React.memo(({ event }) => {
  const { theme } = useTheme();
  const rs = event.runState;

  const rows: Row[] = [];
  if (rs) {
    // Declutter: a pure Q&A turn (no file changes, no findings, no problems)
    // renders NOTHING here — the SuccessCard status row already says  done.
    // The card earns its space only when there is substance to report.
    const hasChanges = (rs.manifest?.created?.length ?? 0) + (rs.manifest?.modified?.length ?? 0) > 0;
    const hasProblem = rs.final?.kind === 'error' || (rs.status ?? '') === 'failed' || (rs.status ?? '') === 'blocked';
    const hasFindings = (event.findings?.length ?? 0) + (rs.findings?.length ?? 0) > 0;
    const hasTodos = (rs.todo || []).some(
      (t) => t.status === 'todo' || t.status === 'in_progress' || t.status === 'blocked',
    );
    if (!hasChanges && !hasProblem && !hasFindings && !hasTodos) {
      return null;
    }

    const status = rs.status || 'idle';
    const outcomeParts: string[] = [];
    if (rs.final?.kind && rs.final.kind !== status) {
      outcomeParts.push(rs.final.kind);
      if (rs.final.code !== undefined && rs.final.code !== null) {
        outcomeParts.push(String(rs.final.code));
      }
    }
    outcomeParts.push(status);
    const outcome = rs.final?.message ? `${outcomeParts.join(' · ')}: ${rs.final.message}` : outcomeParts.join(' · ');
    rows.push({ label: 'outcome', values: [outcome], accent: theme.colors.text.emerald });

    const discovered = (event.findings?.length ? event.findings : rs.findings) || [];
    if (discovered.length > 0) {
      rows.push({
        label: 'discovered',
        values: discovered.slice(0, MAX_ROWS_PER_SECTION),
        accent: theme.colors.status.info,
      });
    }

    const changed = rs.manifest?.created || [];
    if (changed.length > 0) {
      rows.push({
        label: 'changed',
        values: changed.slice(0, MAX_ROWS_PER_SECTION),
        accent: theme.colors.status.info,
      });
    }

    const affected = rs.manifest?.modified || [];
    if (affected.length > 0) {
      rows.push({
        label: 'affected',
        values: affected.slice(0, MAX_ROWS_PER_SECTION),
        accent: theme.colors.status.info,
      });
    }

    let verification = '';
    if (rs.manifest?.completed === true) verification = 'verified';
    else if (rs.manifest?.stalled === true) verification = 'stalled';
    else if (status === 'verifying' || status === 'finalizing' || status === 'completed') verification = status;
    if (verification) {
      rows.push({ label: 'verification', values: [verification], accent: theme.colors.text.dim });
    }

    const unresolved =
      rs.final?.message && (rs.final.kind === 'error' || status === 'failed' || status === 'blocked')
        ? [rs.final.message]
        : [];
    if (unresolved.length > 0) {
      rows.push({ label: 'unresolved', values: unresolved, accent: theme.colors.status.error });
    }

    const next = (rs.todo || [])
      .filter((t) => t.status === 'todo' || t.status === 'in_progress' || t.status === 'blocked')
      .map((t) => t.title)
      .slice(0, MAX_ROWS_PER_SECTION);
    if (next.length > 0) {
      rows.push({ label: 'next', values: next, accent: theme.colors.text.dim });
    }
  }

  if (rows.length === 0 && !event.summary) return null;

  // The header states the real objective from the run-state snapshot (P2.2);
  // the long-form summary text is never rendered as the headline because it
  // can be a multi-section fallback that misrepresents the request.
  const objective = (rs?.objective || '').trim();

  return (
    <Box flexDirection="column" width="100%" paddingX={1} marginBottom={1}>
      <Box flexDirection="row">
        <Text color={theme.colors.status.accent} bold>
          Run summary
        </Text>
        {objective ? (
          <Text color={theme.colors.text.dim}> — {objective}</Text>
        ) : event.summary ? (
          <Text color={theme.colors.text.dim}> — {event.summary}</Text>
        ) : null}
      </Box>
      {rows.map((row) => (
        <Box key={row.label} flexDirection="row">
          <Box flexShrink={0} width={13}>
            <Text color={row.accent}>{row.label}:</Text>
          </Box>
          <Box flexDirection="column" flexShrink={1}>
            {row.values.map((v, i) => (
              <Text key={`${row.label}_${i}`} color={theme.colors.text.dim} wrap="truncate">
                {i === 0 ? v : `  ${v}`}
              </Text>
            ))}
          </Box>
        </Box>
      ))}
    </Box>
  );
});

FinalSummaryCard.displayName = 'FinalSummaryCard';
