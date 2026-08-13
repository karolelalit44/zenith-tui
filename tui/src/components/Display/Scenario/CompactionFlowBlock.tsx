import { Box, Text } from 'ink';
import React from 'react';
import { COMPACTION_PHASE_ORDER } from '../../../config/context';
import { SPINNER_FRAMES } from '../../../constants/animation';
import { useAnimationTick } from '../../../context/AnimationContext';
import { formatTokenCount } from '../../../services/api/tokenEstimationService';
import { useTheme } from '../../../theme/ThemeContext';
import type { CompactionPhase, ContextCompactionFlowEvent } from '../../../types/scenario';

interface CompactionFlowBlockProps {
  event: ContextCompactionFlowEvent;
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

/** Phase colors — calm, minimal tonal shifts (no aggressive warnings). */
function phaseColor(phase: CompactionPhase, themeColors: any): string {
  switch (phase) {
    case 'compacting':
      return themeColors.status.warning;
    case 'ready':
      return themeColors.status.success;
    case 'failed':
      return themeColors.status.warning;
    default:
      return themeColors.status.info;
  }
}

function activePhaseIndex(phase: CompactionPhase): number {
  return COMPACTION_PHASE_ORDER.indexOf(phase);
}

/**
 * One continuous status component for the whole context-compaction lifecycle.
 *
 * It renders a single evolving card (never duplicate rows): the backend emits
 * `context_compaction_started` / `context_compacted` / `context_compaction_ended`
 * which the ScenarioRenderer folds into one `ContextCompactionFlowEvent`. The
 * card advances Preparing → Preserving → Compacting → Verifying → Ready, or
 * shows a calm failure state that leaves the conversation untouched.
 */
export const CompactionFlowBlock: React.FC<CompactionFlowBlockProps> = React.memo(({ event }) => {
  const { theme } = useTheme();
  const tick = useAnimationTick();

  const { phase } = event;
  const color = phaseColor(phase, theme.colors);
  const isActive = phase !== 'ready' && phase !== 'failed';

  // Progress across the phase list (active phases only).
  const idx = activePhaseIndex(phase);
  const progress = idx < 0 ? 0 : (idx + 1) / COMPACTION_PHASE_ORDER.length;
  const filled = Math.round(BAR_WIDTH * progress);

  // Token transition line for the compacting / ready states.
  const tokensPart: string[] = [];
  if (typeof event.beforeTokens === 'number' && typeof event.afterTokens === 'number') {
    tokensPart.push(`${formatTokenCount(event.beforeTokens)} → ${formatTokenCount(event.afterTokens)} tokens`);
  } else if (typeof event.afterTokens === 'number') {
    tokensPart.push(`${formatTokenCount(event.afterTokens)} tokens`);
  }
  if (phase === 'ready' && typeof event.afterTokens === 'number') {
    tokensPart.push(`${formatTokenCount(event.afterTokens)} used`);
  }
  if (phase === 'ready' && typeof event.tokensSaved === 'number' && event.tokensSaved > 0) {
    tokensPart.push(`saved ${formatTokenCount(event.tokensSaved)}`);
  }

  const notes = (event.notes ?? []).slice(0, 3);

  return (
    <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
      <Box flexDirection="row" alignItems="center" width="100%">
        <Box width={2} flexShrink={0}>
          <Text color={color} bold>
            {phase === 'ready'
              ? '✓'
              : phase === 'failed'
                ? '!'
                : isActive
                  ? SPINNER_FRAMES[tick % SPINNER_FRAMES.length]
                  : '•'}
          </Text>
        </Box>

        <Box flexShrink={1} overflow="hidden">
          <Text color={color} bold wrap="truncate-end">
            {PHASE_LABEL[phase]}
            {phase === 'failed' ? '. Conversation unchanged.' : phase === 'ready' ? ' · ' : '…'}
          </Text>
          {phase === 'ready' && tokensPart.length > 0 ? (
            <Text color={theme.colors.text.muted}> {tokensPart.join(' · ')}</Text>
          ) : null}
        </Box>
      </Box>

      {isActive ? (
        <Box flexDirection="row" alignItems="center" paddingLeft={2} marginTop={0}>
          <Box flexGrow={0}>
            <Text color={theme.colors.text.muted}>{'█'.repeat(filled)}</Text>
            <Text color={theme.colors.text.dim}>{'░'.repeat(BAR_WIDTH - filled)}</Text>
          </Box>
          {tokensPart.length > 0 ? (
            <Box marginLeft={1}>
              <Text color={theme.colors.text.muted} wrap="truncate-end">
                {tokensPart.join(' · ')}
              </Text>
            </Box>
          ) : null}
        </Box>
      ) : null}

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
