import { Box, Text } from 'ink';
import React, { useEffect, useRef } from 'react';
import { COMPACTION_PHASE_ORDER } from '../../../config/context';
import { SPINNER_FRAMES } from '../../../constants/animation';
import { useAnimationTick } from '../../../context/AnimationContext';
import { formatTokenCount } from '../../../services/api/tokenEstimationService';
import { modelStore } from '../../../services/providers/ModelStore';
import { useTheme } from '../../../theme/ThemeContext';
import type { CompactionPhase, ContextCompactionFlowEvent } from '../../../types/scenario';
import { formatDuration } from '../../../utils/text';
import type { EventRenderContext } from './componentRegistry';
import { TerminalMarkdown } from './TerminalMarkdown';

interface CompactionFlowBlockProps {
  event: ContextCompactionFlowEvent;
  context?: EventRenderContext;
}

const BAR_WIDTH = 18;

const PHASE_LABEL: Record<CompactionPhase, string> = {
  preparing: 'Preparing conversation context',
  preserving: 'Preserving important context',
  compacting: 'Compacting context',
  verifying: 'Verifying preserved context',
  ready: 'Context ready',
  failed: 'Unable to safely compact context',
};

/** Phase accent color for the live status row. */
function phaseColor(phase: CompactionPhase, themeColors: any): string {
  switch (phase) {
    case 'compacting':
      return themeColors.status.warning;
    case 'failed':
      return themeColors.status.warning;
    case 'ready':
      return themeColors.status.success;
    default:
      return themeColors.status.info;
  }
}

function activePhaseIndex(phase: CompactionPhase): number {
  return COMPACTION_PHASE_ORDER.indexOf(phase);
}

const PRESERVED_LABELS: [key: string, label: string][] = [
  ['requirements', 'requirement'],
  ['decisions', 'decision'],
  ['openTasks', 'open task'],
  ['findings', 'finding'],
  ['artifacts', 'artifact'],
  ['agents', 'agent'],
];

function pluralize(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? '' : 's'}`;
}

/**
 * One continuous status component for the whole context-compaction lifecycle.
 *
 * Renders a single evolving "Compaction" card (never duplicate rows): the
 * backend emits `context_compaction_started` / `context_compacted` /
 * `context_compaction_ended` which the ScenarioRenderer folds into one
 * `ContextCompactionFlowEvent`. The card advances Preparing → Preserving →
 * Compacting → Verifying → Ready, or shows a calm failure state that leaves
 * the conversation untouched. On completion it becomes a summary card with the
 * before/after token transition, the preserved-context breakdown, and the
 * human-readable compaction summary emitted by the backend.
 */
export const CompactionFlowBlock: React.FC<CompactionFlowBlockProps> = React.memo(({ event, context }) => {
  const { theme } = useTheme();
  const tick = useAnimationTick();
  const historical = context?.isHistorical ?? false;

  // Measure elapsed time from first render → terminal phase so the card can
  // show its real runtime. Historical renders (already-committed turns) mount
  // straight into the ready state, so their duration is omitted.
  const startRef = useRef(Date.now());
  const endRef = useRef<number | null>(null);
  useEffect(() => {
    if (event.phase === 'ready' || event.phase === 'failed') {
      endRef.current = endRef.current ?? Date.now();
    }
  }, [event.phase]);

  const { phase } = event;
  const isActive = phase !== 'ready' && phase !== 'failed';
  const durationMs = endRef.current !== null ? endRef.current - startRef.current : Date.now() - startRef.current;
  const durationStr = endRef.current !== null && !historical ? formatDuration(durationMs) : '';

  const color = phaseColor(phase, theme.colors);
  const idx = activePhaseIndex(phase);
  const progress = idx < 0 ? 0 : (idx + 1) / COMPACTION_PHASE_ORDER.length;
  const filled = Math.round(BAR_WIDTH * progress);

  const modelLabel = modelStore.current ? modelStore.toDisplayString(modelStore.current) : '';

  // Token transition line shared between the live progress row and the summary.
  const transitionStr =
    typeof event.beforeTokens === 'number' && typeof event.afterTokens === 'number'
      ? `${formatTokenCount(event.beforeTokens)} → ${formatTokenCount(event.afterTokens)} tokens`
      : typeof event.afterTokens === 'number'
        ? `${formatTokenCount(event.afterTokens)} tokens`
        : null;
  const savedStr =
    typeof event.tokensSaved === 'number' && event.tokensSaved > 0
      ? `saved ${formatTokenCount(event.tokensSaved)} tokens`
      : null;

  const preserved =
    event.preserved && typeof event.preserved === 'object'
      ? (event.preserved as Record<string, number | undefined>)
      : undefined;
  const preservedStr = preserved
    ? PRESERVED_LABELS.map(([key, label]) => {
        const value = preserved[key];
        return typeof value === 'number' ? pluralize(value, label) : null;
      })
        .filter((part): part is string => part !== null)
        .join(' · ')
    : '';

  const notes = (event.notes ?? []).slice(0, 3);

  return (
    <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
      {/* ── Card header: branded, model, runtime ── */}
      <Box flexDirection="row" alignItems="center" width="100%" flexWrap="nowrap">
        <Text color={theme.colors.status.info} bold>
          ▣ Compaction
        </Text>
        {modelLabel ? (
          <Text color={theme.colors.text.muted}>
            {' '}
            · <Text color={theme.colors.text.dim}>{modelLabel}</Text>
          </Text>
        ) : null}
        {durationStr ? <Text color={theme.colors.text.muted}> · {durationStr}</Text> : null}
      </Box>

      {isActive ? (
        <>
          <Box flexDirection="row" alignItems="center" paddingLeft={2} marginTop={0}>
            <Box width={2} flexShrink={0}>
              <Text color={color} bold>
                {SPINNER_FRAMES[tick % SPINNER_FRAMES.length]}
              </Text>
            </Box>
            <Text color={color} bold wrap="truncate-end">
              {PHASE_LABEL[phase]}…
            </Text>
            {transitionStr ? <Text color={theme.colors.text.muted}> {transitionStr}</Text> : null}
          </Box>
          <Box flexDirection="row" alignItems="center" paddingLeft={2} marginTop={0}>
            <Box flexGrow={0}>
              <Text color={theme.colors.text.muted}>{'█'.repeat(filled)}</Text>
              <Text color={theme.colors.text.dim}>{'░'.repeat(BAR_WIDTH - filled)}</Text>
            </Box>
            {savedStr ? (
              <Text color={theme.colors.text.muted} wrap="truncate-end">
                {' '}
                {savedStr}
              </Text>
            ) : null}
          </Box>
        </>
      ) : phase === 'failed' ? (
        <>
          <Box flexDirection="row" alignItems="center" paddingLeft={2} marginTop={0}>
            <Box width={2} flexShrink={0}>
              <Text color={theme.colors.status.warning} bold>
                ✕
              </Text>
            </Box>
            <Text color={theme.colors.status.warning} bold>
              Unable to safely compact context
            </Text>
          </Box>
          <Box paddingLeft={2}>
            <Text color={theme.colors.text.muted}>Conversation unchanged.</Text>
          </Box>
        </>
      ) : (
        <>
          {/* ── Completion banner: manual compaction summary strip ── */}
          <Box paddingLeft={2} marginTop={0}>
            <Text color={theme.colors.status.success} bold wrap="truncate-end">
              ✻ Context compacted (manual) · {[transitionStr, savedStr].filter(Boolean).join(' · ')} ✻
            </Text>
          </Box>

          {/* ── Human-readable summary body (structured markdown) ── */}
          {event.summary ? (
            <Box paddingLeft={2} marginTop={0} flexDirection="column">
              <TerminalMarkdown content={event.summary} />
            </Box>
          ) : null}

          {/* ── Preserved context breakdown ── */}
          {preservedStr ? (
            <Box paddingLeft={2} marginTop={0}>
              <Text color={theme.colors.text.dim} wrap="truncate-end">
                Preserved · {preservedStr}
              </Text>
            </Box>
          ) : null}
        </>
      )}

      {notes.length > 0 ? (
        <Box flexDirection="column" paddingLeft={3} marginTop={0}>
          {notes.map((note, noteIdx) => (
            <Text key={noteIdx} color={theme.colors.text.dim} wrap="truncate-end">
              ↳ {note}
            </Text>
          ))}
        </Box>
      ) : null}
    </Box>
  );
});

CompactionFlowBlock.displayName = 'CompactionFlowBlock';
