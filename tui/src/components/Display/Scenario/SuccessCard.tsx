import { Box, Text } from 'ink';
import React, { useRef } from 'react';
import { useAnimationTick } from '../../../context/AnimationContext';
import { estimateTokensForEvents, formatTokenCount } from '../../../services/api/tokenEstimationService';
import { useTheme } from '../../../theme/ThemeContext';
import type { ScenarioEvent, SuccessEvent, TurnManifestEvent } from '../../../types/scenario';
import { formatDuration } from '../../../utils/text';
import type { EventRenderContext } from './componentRegistry';

interface SuccessCardProps {
  event: SuccessEvent;
  context?: EventRenderContext;
  manifest?: TurnManifestEvent;
  turnEvents?: ScenarioEvent[];
}

/** Waveform bar characters for animated equalizer. */
const WAVE_FRAMES = ['▁', '▂', '▃', '▄', '▅', '▆', '▇', '█', '▇', '▆', '▅', '▄', '▃', '▂'] as const;

export const SuccessCard: React.FC<SuccessCardProps> = React.memo(({ event, context, turnEvents }) => {
  const { theme } = useTheme();
  const tick = useAnimationTick();

  const isLiveRunning = Boolean(context?.isRunning && !context?.isHistorical);

  // Gradient colors for equalizer animation while running
  const gradient = [
    theme.colors.status.accent,
    theme.colors.text.emerald,
    theme.colors.status.success,
    theme.colors.status.info,
  ];

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
  const durationStr = elapsedMs ? formatDuration(elapsedMs) : '';

  // Used tokens calculation. Authoritative priority:
  // 1. Provider cumulative runTotal if reported and non-zero
  // 2. Composed context occupancy (used) if reported and non-zero
  // 3. Recorded token telemetry in turnEvents (token_usage_recorded / context_updated)
  // 4. Character-based estimation from turnEvents content
  const reportedRunTotal =
    typeof event.tokenInfo?.runTotal === 'number' && event.tokenInfo.runTotal > 0
      ? event.tokenInfo.runTotal
      : undefined;
  const reportedUsed =
    typeof event.tokenInfo?.used === 'number' && event.tokenInfo.used > 0 ? event.tokenInfo.used : undefined;

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

  const finalReportedTokens = reportedRunTotal ?? reportedUsed ?? turnRecordedTokens;
  const usedTokens =
    finalReportedTokens !== undefined ? finalReportedTokens : turnEvents ? estimateTokensForEvents(turnEvents) : 0;
  const tokenStr = usedTokens > 0 ? `${formatTokenCount(usedTokens)} tokens` : '';

  const metricsParts: string[] = [];
  const rawIters =
    event.iterations !== undefined && event.iterations > 0
      ? event.iterations
      : !isLiveRunning
        ? Math.max(
            1,
            turnEvents ? turnEvents.filter((e) => e.kind === 'tool_step' || e.kind === 'tool_call').length : 1,
          )
        : undefined;
  const iters = rawIters !== undefined ? Math.max(1, rawIters) : undefined;

  if (iters !== undefined) {
    metricsParts.push(`${iters} iter${iters === 1 ? '' : 's'}`);
  }
  if (durationStr) {
    metricsParts.push(durationStr);
  }
  if (tokenStr) {
    metricsParts.push(tokenStr);
  }

  const metricsText = metricsParts.length > 0 ? metricsParts.join(' · ') : 'done';

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
          <Box flexDirection="row" marginRight={1} alignItems="flex-end">
            {Array.from({ length: 3 }).map((_, idx) => {
              const phase = (Math.sin(tick / 3 + idx * 0.85) + 1) / 2;
              const frameIdx = Math.max(
                0,
                Math.min(WAVE_FRAMES.length - 1, Math.floor(phase * (WAVE_FRAMES.length - 1))),
              );
              const color = gradient[(idx + Math.floor(tick / 3)) % gradient.length];
              return (
                <Box key={idx} width={1}>
                  <Text color={color}>{WAVE_FRAMES[frameIdx]}</Text>
                </Box>
              );
            })}
          </Box>
        ) : (
          <Box marginRight={1}>
            <Text color={theme.colors.status.success} bold>
              ●
            </Text>
          </Box>
        )}

        <Text color={theme.colors.text.muted}>{metricsText}</Text>
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
