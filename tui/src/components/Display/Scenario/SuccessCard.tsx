import { Box, Text } from 'ink';
import React, { useRef } from 'react';
import { useAnimationTick } from '../../../context/AnimationContext';
import { estimateTokensForEvents, formatTokenCount } from '../../../services/api/tokenEstimationService';
import { useTheme } from '../../../theme/ThemeContext';
import type { ScenarioEvent, SuccessEvent, TurnManifestEvent } from '../../../types/scenario';
import { formatDuration } from '../../../utils/text';
import { LiveElapsed } from '../../ui/LiveElapsed';
import type { EventRenderContext } from './componentRegistry';

interface SuccessCardProps {
  event: SuccessEvent;
  context?: EventRenderContext;
  manifest?: TurnManifestEvent;
  turnEvents?: ScenarioEvent[];
}

/** Core glyph per breath tick: dim quiet → charge → ignited Zenith core → release. */
const RETICLE_FRAMES = ['*', '+', '⨳', '+', '*'] as const;

/**
 * Isolated 100ms-tick reticle pulse: the four-fold core presses through the
 * quiet dim `*`, charges as `+`, and ignites into the bold `⨳` Zenith core
 * before releasing. Symmetric `·` rays frame it, and every glyph is colored
 * purely from the theme. Only this tiny node subscribes to the shared tick
 * while the turn runs; the memoized SuccessCard never re-renders per tick.
 */
const ReticlePulse: React.FC = React.memo(() => {
  const { theme } = useTheme();
  const tick = useAnimationTick();
  const core = RETICLE_FRAMES[tick % RETICLE_FRAMES.length];
  const color = core === '*' ? theme.colors.text.dim : theme.colors.status.info;
  return (
    <Box flexDirection="row" marginRight={1} alignItems="center">
      <Text color={theme.colors.text.dim}>{'·'}</Text>
      <Text color={color} bold={core === '⨳'}>
        {core}
      </Text>
      <Text color={theme.colors.text.dim}>{'·'}</Text>
    </Box>
  );
});

ReticlePulse.displayName = 'ReticlePulse';

export const SuccessCard: React.FC<SuccessCardProps> = React.memo(({ event, context, manifest, turnEvents }) => {
  const { theme } = useTheme();

  const isLiveRunning = Boolean(context?.isRunning && !context?.isHistorical);

  // Duration in whole 1-second increments (updates only on 1s changes).
  // Prefer the server-reported elapsedMs. The shared tick is ONLY a render
  // signal — `tick * 100` would measure time since APP LAUNCH (the tick
  // counter is global and never resets per turn), which showed absurd
  // durations like "32 minutes" on a fresh turn. Measure from this card's
  // own mount instead, mirroring ToolStepCard's pendingStartRef pattern.
  const runStartRef = useRef<number | null>(null);
  if (isLiveRunning && runStartRef.current === null) {
    runStartRef.current = Date.now();
  }
  const reportedElapsedMs = typeof event.elapsedMs === 'number' && event.elapsedMs > 0 ? event.elapsedMs : 0;
  const liveElapsedMs =
    isLiveRunning && runStartRef.current !== null ? Math.max(1000, Date.now() - runStartRef.current) : undefined;
  let elapsedMs = reportedElapsedMs > 0 ? reportedElapsedMs : liveElapsedMs;

  if (!elapsedMs && !isLiveRunning) {
    // If completed/historical and no direct elapsedMs was reported, sum durations from events (thinking, tool steps)
    const eventDurations = turnEvents
      ? turnEvents.reduce((acc, ev) => {
          if ('duration' in ev && typeof (ev as { duration?: unknown }).duration === 'number') {
            const d = (ev as { duration: number }).duration;
            if (d > 0) return acc + d;
          }
          return acc;
        }, 0)
      : 0;
    elapsedMs = eventDurations > 0 ? eventDurations : 1000;
  }
  const durationStr = formatDuration(elapsedMs || 1000);

  // Used tokens calculation. Authoritative priority:
  // 1. Composed context occupancy / turn tokens (used) if reported and non-zero
  // 2. Provider cumulative runTotal if reported and non-zero
  // 3. Recorded token telemetry in turnEvents (token_usage_recorded / context_updated)
  // 4. Character-based estimation from turnEvents content
  const reportedUsed =
    typeof event.tokenInfo?.used === 'number' && event.tokenInfo.used > 0 ? event.tokenInfo.used : undefined;
  const reportedRunTotal =
    typeof event.tokenInfo?.runTotal === 'number' && event.tokenInfo.runTotal > 0
      ? event.tokenInfo.runTotal
      : undefined;

  let turnRecordedTokens: number | undefined;
  if (turnEvents) {
    for (const te of turnEvents) {
      if (te.kind === 'token_usage_recorded' && typeof te.totalTokens === 'number' && te.totalTokens > 0) {
        turnRecordedTokens = te.totalTokens;
        break;
      }
      if (te.kind === 'context_updated' && typeof te.used === 'number' && te.used > 0) {
        turnRecordedTokens = te.used;
      }
    }
  }

  const finalReportedTokens = reportedUsed ?? reportedRunTotal ?? turnRecordedTokens;
  const rawEstimated = turnEvents ? estimateTokensForEvents(turnEvents) : 0;
  const usedTokens =
    finalReportedTokens !== undefined
      ? finalReportedTokens
      : rawEstimated > 0
        ? rawEstimated
        : turnEvents && turnEvents.length > 0
          ? 1
          : 0;
  const tokenStr = usedTokens > 0 ? `${formatTokenCount(usedTokens)} tokens` : '';

  const effectiveManifest = manifest ?? event.manifest;
  const isTruncated =
    event.truncated === true ||
    event.finishReason === 'length' ||
    Boolean(effectiveManifest?.remaining?.some((r) => r.toLowerCase().includes('token limit')));
  const isComplete =
    !isTruncated && event.completed !== false && (!effectiveManifest || effectiveManifest.completed !== false);

  const metricsParts: (string | React.ReactNode)[] = [];
  const rawIters =
    event.iterations !== undefined && event.iterations > 0
      ? event.iterations
      : Math.max(1, turnEvents ? turnEvents.filter((e) => e.kind === 'tool_step' || e.kind === 'tool_call').length : 1);
  const iters = rawIters !== undefined ? Math.max(1, rawIters) : undefined;

  if (iters !== undefined) {
    metricsParts.push(`${iters} iter${iters === 1 ? '' : 's'}`);
  }
  if (durationStr) {
    metricsParts.push(
      isLiveRunning && runStartRef.current !== null ? (
        <LiveElapsed key="live" startedAt={runStartRef.current} prefix="" />
      ) : (
        durationStr
      ),
    );
  }
  if (tokenStr) {
    metricsParts.push(tokenStr);
  }
  if (!isComplete) {
    if (isTruncated) {
      metricsParts.push('truncated · token limit');
    } else if (effectiveManifest?.remaining && effectiveManifest.remaining.length > 0) {
      metricsParts.push(`${effectiveManifest.remaining.length} remaining`);
    } else {
      metricsParts.push('tasks remaining');
    }
  }

  const metricsNode =
    metricsParts.length > 0
      ? metricsParts.map((part, i) => (
          <React.Fragment key={i}>
            {i > 0 ? ' · ' : ''}
            {part}
          </React.Fragment>
        ))
      : isComplete
        ? 'done'
        : isTruncated
          ? 'truncated'
          : 'incomplete';

  return (
    <Box
      flexDirection="row"
      width="100%"
      justifyContent="space-between"
      alignItems="center"
      paddingX={1}
      marginBottom={1}
    >
      {/* Left Section: Animated Equalizer Wave (Running) / Status Glyph (Completed/Interrupted) + Metrics */}
      <Box flexDirection="row" alignItems="center" flexShrink={1}>
        {isLiveRunning ? (
          <ReticlePulse />
        ) : !isComplete ? (
          <Box marginRight={1}>
            <Text color={theme.colors.status.warning} bold>
              ▲
            </Text>
          </Box>
        ) : (
          <Box marginRight={1}>
            <Text color={theme.colors.status.success} bold>
              ●
            </Text>
          </Box>
        )}

        <Text color={theme.colors.text.muted}>{metricsNode}</Text>
      </Box>

      {/* Right Section: Esc to cancel while running (hidden when completed or interrupted) */}
      {isLiveRunning ? (
        <Box flexShrink={0} marginLeft={1}>
          <Text color={theme.colors.text.dim}>Esc to cancel</Text>
        </Box>
      ) : null}
    </Box>
  );
});

SuccessCard.displayName = 'SuccessCard';
