import { estimateTokensForEvents } from '../services/api/tokenEstimationService';
import type { ScenarioEvent, SuccessEvent } from '../types/scenario';
import { formatRunTokens } from './footerLayout';
import { formatDuration } from './text';

export interface TurnUsage {
  tokens?: number;
  durationMs?: number;
}

/**
 * Resolve ONE turn's cost telemetry from its committed event list. This is the
 * single source of truth for the per-prompt cost line rendered after each user
 * message once the model completes:
 *   - Tokens prefer the backend success event (context occupancy, then run
 *     total), falling back to the frontend character estimate.
 *   - Duration prefers the success event's elapsedMs, else the sum of event
 *     durations.
 */
export function resolveTurnUsage(events: ScenarioEvent[]): TurnUsage {
  const success: SuccessEvent | undefined = events.find((e): e is SuccessEvent => e.kind === 'success');

  let tokens: number | undefined;
  if (success?.tokenInfo) {
    const used = typeof success.tokenInfo.used === 'number' ? success.tokenInfo.used : 0;
    const runTotal = typeof success.tokenInfo.runTotal === 'number' ? success.tokenInfo.runTotal : 0;
    if (used > 0) {
      tokens = used;
    } else if (runTotal > 0) {
      tokens = runTotal;
    }
  }
  if (tokens === undefined || tokens <= 0) {
    const est = estimateTokensForEvents(events);
    if (est > 0) tokens = est;
  }

  let durationMs: number | undefined;
  if (typeof success?.elapsedMs === 'number' && success.elapsedMs > 0) {
    durationMs = success.elapsedMs;
  } else {
    const sum = events.reduce((acc, ev) => {
      const d = (ev as { duration?: unknown }).duration;
      if (typeof d === 'number' && d > 0) return acc + d;
      return acc;
    }, 0);
    if (sum > 0) durationMs = sum;
  }

  return {
    tokens: typeof tokens === 'number' && tokens > 0 ? tokens : undefined,
    durationMs: typeof durationMs === 'number' && durationMs > 0 ? durationMs : undefined,
  };
}

/** Render a turn's cost compactly: "+25.7K (45 s)". Empty when nothing known. */
export function formatTurnCost(usage: TurnUsage): string {
  const parts: string[] = [];
  if (usage.tokens !== undefined && usage.tokens > 0) {
    parts.push(`+${formatRunTokens(usage.tokens)}`);
  }
  if (usage.durationMs !== undefined && usage.durationMs > 0) {
    parts.push(`(${formatDuration(usage.durationMs)})`);
  }
  return parts.join(' ');
}
