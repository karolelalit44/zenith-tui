import type { CompactionPhase } from '../types/scenario';
import { envFloat } from './env';

export type ContextLevel = 'neutral' | 'attention' | 'preparing' | 'required';

export interface ContextThresholds {
  /** Fraction (0..1) of context used above which the indicator turns "attention". */
  attention: number;
  /** Fraction above which compaction is "preparing". */
  preparing: number;
  /** Fraction above which compaction is "required". */
  required: number;
}

function clamp01(fraction: number): number {
  return Math.max(0, Math.min(1, fraction));
}

/** Configurable context-pressure thresholds (from tui/.env, model-agnostic). */
export const contextThresholds: ContextThresholds = Object.freeze({
  attention: clamp01(envFloat('ZENITH_CONTEXT_ATTENTION')),
  preparing: clamp01(envFloat('ZENITH_CONTEXT_PREPARING')),
  required: clamp01(envFloat('ZENITH_CONTEXT_REQUIRED')),
});

/** Ordered compaction phases for the continuous status component. */
export const COMPACTION_PHASE_ORDER: readonly CompactionPhase[] = [
  'preparing',
  'preserving',
  'compacting',
  'verifying',
  'ready',
];

/**
 * Single source of truth for compaction trigger labels. The UI must never
 * guess the trigger: wire data carries `trigger` (`automatic` | `manual`);
 * anything else falls back to the label of the TUI-invoked (manual) path.
 */
export const COMPACTION_TRIGGER_LABELS: Record<string, string> = Object.freeze({
  automatic: 'automatic',
  manual: 'manual',
});

/** Map a context-used fraction (0..1) to a tonal level. */
export function contextLevelForFraction(fraction: number): ContextLevel {
  if (fraction >= contextThresholds.required) return 'required';
  if (fraction >= contextThresholds.preparing) return 'preparing';
  if (fraction >= contextThresholds.attention) return 'attention';
  return 'neutral';
}

export function contextLevelForPercent(percent: number): ContextLevel {
  return contextLevelForFraction(percent / 100);
}

/** Short suffix shown on the compact indicator for non-neutral levels. */
export function contextLabel(level: ContextLevel): string | null {
  switch (level) {
    case 'preparing':
      return 'Preparing';
    case 'required':
      return 'Compaction required';
    default:
      return null;
  }
}

/** Semantic color tokens per context level (mapped to theme colors by the UI). */
export type ContextColor = 'dim' | 'info' | 'warning';

export function contextColor(level: ContextLevel): ContextColor {
  switch (level) {
    case 'required':
      return 'warning';
    case 'preparing':
      return 'info';
    default:
      return 'dim';
  }
}
