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
  const reportedElapsedMs = event.elapsedMs ?? 0;
  const liveElapsedMs =
    isLiveRunning && runStartRef.current !== null ? Math.max(1000, Date.now() - runStartRef.current) : undefined;
  const elapsedMs = reportedElapsedMs > 0 ? reportedElapsedMs : liveElapsedMs;
  const durationStr = elapsedMs ? formatDuration(elapsedMs) : '';

  // Used tokens calculation. `tokenInfo.used` is the composed-context occupancy
  // reported by the backend and is authoritative whenever non-zero; `estimated`
  // only describes the cumulative *run* usage and must not suppress it. Fall
  // back to the frontend estimate only when usage is missing or zero.
  const reportedUsed = event.tokenInfo?.used ?? 0;
  const usageIsUnknown = reportedUsed <= 0 || event.tokenInfo === undefined;
  const usedTokens = usageIsUnknown ? (turnEvents ? estimateTokensForEvents(turnEvents) : 0) : reportedUsed;
  const tokenStr = usedTokens > 0 ? `${formatTokenCount(usedTokens)} tokens` : '';

  const metricsParts: string[] = [];
  const iters =
    event.iterations !== undefined
      ? event.iterations
      : !isLiveRunning
        ? Math.max(
          1,
          turnEvents ? turnEvents.filter((e) => e.kind === 'tool_step' || e.kind === 'tool_call').length : 1,
        )
        : undefined;

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
      {/* Left Section: Animated Equalizer Wave (Running) / Checkmark (Completed/Interrupted) + Metrics */}
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
          <Text color={theme.colors.status.success} bold>
            {' '}
          </Text>
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
