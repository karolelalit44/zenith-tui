import type { CompactionPhase } from '../types/scenario';

export type ContextLevel = 'neutral' | 'attention' | 'preparing' | 'required';

export interface ContextThresholds {
  /** Fraction (0..1) of context used above which the indicator turns "attention". */
  attention: number;
  /** Fraction above which compaction is "preparing". */
  preparing: number;
  /** Fraction above which compaction is "required". */
  required: number;
}

export const DEFAULT_CONTEXT_THRESHOLDS: ContextThresholds = {
  attention: 0.7,
  preparing: 0.85,
  required: 0.95,
};

function readThreshold(env: string | undefined, fallback: number): number {
  if (env === undefined || env.trim() === '') return fallback;
  const n = Number.parseFloat(env.trim());
  if (Number.isNaN(n)) return fallback;
  return Math.max(0, Math.min(1, n));
}

/** Configurable context-pressure thresholds. Overridable via env, model-agnostic. */
export const contextThresholds: ContextThresholds = Object.freeze({
  attention: readThreshold(process.env.ZENITH_CONTEXT_ATTENTION, DEFAULT_CONTEXT_THRESHOLDS.attention),
  preparing: readThreshold(process.env.ZENITH_CONTEXT_PREPARING, DEFAULT_CONTEXT_THRESHOLDS.preparing),
  required: readThreshold(process.env.ZENITH_CONTEXT_REQUIRED, DEFAULT_CONTEXT_THRESHOLDS.required),
});

/** Ordered compaction phases for the continuous status component. */
export const COMPACTION_PHASE_ORDER: readonly CompactionPhase[] = [
  'preparing',
  'preserving',
  'compacting',
  'verifying',
  'ready',
];

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
