import { Box, Text } from 'ink';
import React, { useRef } from 'react';
import {
  BACKEND_RESPONSE_PLACEHOLDER_LABEL,
  BACKEND_RESPONSE_PLACEHOLDER_PHRASES,
  LIVE_PROGRESS_EVENT_ID,
} from '../../../constants/events';
import {
  isZenithBright,
  isZenithDim,
  zenithPulseGlyphForTick,
} from '../../../constants/animation';
import { useAnimationTick } from '../../../context/AnimationContext';
import { useTheme } from '../../../theme/ThemeContext';
import type { ProgressEvent } from '../../../types/scenario';
import { Spinner } from '../../ui/Spinner';

interface ProgressBarProps {
  event: ProgressEvent;
}

/**
 * Compact live activity row for agent tool execution.
 *
 * One line: current-step status icon + label, with a dim done/total counter.
 * The old design (big percent bar + full checklist) stacked visual noise on
 * every snapshot; all the information a user needs while a turn runs is
 * WHAT is running right now and HOW MUCH is left.
 *
 * Rows that merely echo an in-flight tool (same command the terminal window
 * card already shows) are suppressed upstream — see
 * `progressDuplicatesPendingToolStep`. Esc-to-cancel lives ONLY on the
 * turn-level status row so the affordance is unique.
 *
 * Empty-steps progress (the awaiting-backend latency placeholder) renders as
 * AwaitingBackendRow below — a breathing Zenith reticle with rotating
 * phrases, animated ellipsis, and elapsed timer.
 */
const AWAITING_DOTS = ['', '·', '··', '···'] as const;
/** Ticks (100ms each) per rotating phrase — ~2.4s per phrase. */
const PHRASE_TICKS = 24;

/**
 * Modern awaiting-backend row — replaces the old static
 * "· Waiting for backend response" line.
 * Breathing reticle + rotating phrases + animated ellipsis + elapsed timer.
 * Isolated tick leaf so only this row re-renders per 100ms.
 */

const AwaitingBackendRow: React.FC = React.memo(() => {
  const { theme } = useTheme();
  const tick = useAnimationTick();
  const startedAt = useRef(Date.now());

  const phrase =
    BACKEND_RESPONSE_PLACEHOLDER_PHRASES[
      Math.floor(tick / PHRASE_TICKS) % BACKEND_RESPONSE_PLACEHOLDER_PHRASES.length
    ] ?? BACKEND_RESPONSE_PLACEHOLDER_LABEL;
  const dots = AWAITING_DOTS[Math.floor(tick / 4) % AWAITING_DOTS.length];
  const glyph = zenithPulseGlyphForTick(tick);
  const elapsedS = Math.max(0, Math.floor((Date.now() - startedAt.current) / 1000));

  return (
    <Box flexDirection="row" width="100%" marginBottom={1} paddingX={1} alignItems="center">
      <Box width={2} flexShrink={0}>
        <Text color={theme.colors.status.info} dimColor={isZenithDim(glyph)} bold={isZenithBright(glyph)}>
          {glyph}
        </Text>
      </Box>
      <Text color={theme.colors.text.bright} bold wrap="truncate-end">
        {phrase}
        <Text color={theme.colors.status.info}>{dots}</Text>
      </Text>
      <Text color={theme.colors.text.dim}>
        {'  · '}
        {elapsedS}s
      </Text>
    </Box>
  );
});

AwaitingBackendRow.displayName = 'AwaitingBackendRow';

export const ProgressBar: React.FC<ProgressBarProps> = React.memo(({ event }) => {
  const { theme } = useTheme();

  // Empty-steps progress is always the latency placeholder (live id, or the
  // stable label when replayed). Give it the animated treatment instead of
  // falling through to the static '·' icon path below.
  if (
    event.steps.length === 0 &&
    (event.id === LIVE_PROGRESS_EVENT_ID || event.label === BACKEND_RESPONSE_PLACEHOLDER_LABEL)
  ) {
    return <AwaitingBackendRow />;
  }

  const steps = event.steps;
  const activeIdx = steps.findIndex((s) => s.status === 'active');
  const lastIdx = steps.length - 1;
  const current = steps[activeIdx >= 0 ? activeIdx : lastIdx];
  const doneCount = steps.filter((s) => s.status === 'done').length;
  const isActive = current?.status === 'active';

  let icon = '·';
  let iconColor = theme.colors.text.dim;
  if (isActive) {
    iconColor = theme.colors.text.ethereal;
  } else if (current?.status === 'error') {
    icon = '✗';
    iconColor = theme.colors.status.error;
  } else if (steps.length > 0 && doneCount === steps.length) {
    icon = '';
    iconColor = theme.colors.status.success;
  }

  return (
    <Box flexDirection="row" width="100%" marginBottom={1} paddingX={1} alignItems="center">
      <Box width={2} flexShrink={0}>
        {isActive ? <Spinner color={theme.colors.text.ethereal} /> : <Text color={iconColor}>{icon}</Text>}
      </Box>
      <Text color={theme.colors.text.bright} wrap="truncate-end">
        {current?.label ?? event.label}
      </Text>
      {steps.length > 1 && (
        <Text color={theme.colors.text.muted}>
          {' '}
          {doneCount}/{steps.length}
        </Text>
      )}
      {typeof event.percent === 'number' && event.percent > 0 && event.percent < 100 && (
        <Text color={theme.colors.text.muted}> · {Math.round(event.percent)}%</Text>
      )}
    </Box>
  );
});

ProgressBar.displayName = 'ProgressBar';
