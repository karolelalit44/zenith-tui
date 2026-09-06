import type { ScenarioMode } from '../types/scenario';
import { truncateEnd, truncateStart } from './text';
import { getWorkspaceFolderName } from './workspacePath';

export const FOOTER_EDGE_PAD = 6;
const FOOTER_MIN_PROVIDER_LEN = 6;

export interface FooterLayoutInput {
  columns: number;
  mode: ScenarioMode;
  chip: string;
  providerName: string;
  dir: string;
  branch: string;
  effectiveMaxTokens?: number;
  /** Cumulative run/API token usage (telemetry). */
  runTokens?: number;
  /** True when the cumulative run usage is estimated, not provider-reported. */
  runEstimated?: boolean;
  /** Composed-context occupancy percent (0–100). Omitted → no gauge renders. */
  contextPercent?: number;
  /** True when the context-window denominator is a fallback estimate. */
  windowEstimated?: boolean;
}

export interface FooterLayoutOutput {
  modeLabel: string;
  chip: string;
  provider: string;
  dir: string;
  dirText: string;
  branch: string;
  branchText: string;
  pathBranch: string;
  tokenCount: string;
  tokenUsage: string;
  maxTokens: string;
  gauge: string;
  showGauge: boolean;
  scopeLabel: string;
}

/** Compact cumulative run/API token telemetry (e.g. 12.4K, 1.2M, 420). */
export function formatRunTokens(count: number): string {
  if (count <= 0) return '0';
  if (count >= 1_000_000) return `${(count / 1_000_000).toFixed(1)}M`;
  if (count >= 1_000) return `${(count / 1_000).toFixed(1)}K`;
  return String(count);
}

export function computeFooterLayout(input: FooterLayoutInput): FooterLayoutOutput {
  const contentWidth = Math.max(24, input.columns - FOOTER_EDGE_PAD);
  const modeLabel = input.mode === 'plan' ? '[PLAN] ' : '[BUILD] ';

  const gaugePercent =
    typeof input.contextPercent === 'number' ? Math.max(0, Math.min(100, input.contextPercent)) : null;
  const gauge = '';
  const showGauge = false;

  const runCount = typeof input.runTokens === 'number' ? input.runTokens : 0;
  const hasRunUsage = runCount > 0 || typeof input.runTokens === 'number';
  const tokenStr = hasRunUsage ? `${formatRunTokens(runCount)} tok` : '';
  const ctxStr =
    gaugePercent !== null && (runCount > 0 || typeof input.runTokens !== 'number')
      ? `${gaugePercent.toFixed(1)}% ctx`
      : '';

  const parts = [tokenStr];
  if (ctxStr) {
    parts.push(ctxStr);
  }

  const tokenUsage = parts.filter(Boolean).join(' · ');
  const tokenCount = tokenUsage;
  const maxTokens =
    typeof input.effectiveMaxTokens === 'number' && input.effectiveMaxTokens > 0 ? `${input.effectiveMaxTokens}` : '0';
  const scopeLabel = '';

  const cleanBranch = input.branch ? input.branch.replace(/^\(+|\)+$/g, '').trim() : '';

  const rawDir = getWorkspaceFolderName(input.dir);

  const rightText = tokenUsage;
  const tokenWidth = rightText.length + (rightText ? 1 : 0);
  const colonWidth = rawDir && cleanBranch ? 1 : 0;
  const fixedRight = tokenWidth + colonWidth + 1;
  const fixedLeft = modeLabel.length + 2;

  let available = contentWidth - fixedLeft - fixedRight;

  const branchBudget = Math.max(1, Math.min(cleanBranch.length, Math.floor(available * 0.5)));
  const branchText = truncateEnd(cleanBranch, branchBudget);
  available = Math.max(0, available - branchText.length);

  const dirBudget = Math.max(1, available);
  const dirText = truncateStart(rawDir, dirBudget);
  available = Math.max(0, available - dirText.length);

  const chipBudget = Math.max(1, available);
  const chipText = truncateEnd(input.chip, chipBudget);
  available = Math.max(0, available - chipText.length);

  let provider = '';
  if (available >= FOOTER_MIN_PROVIDER_LEN && input.providerName) {
    const name = truncateEnd(input.providerName, available - 3);
    provider = ` · ${name}`;
  }

  let pathBranch = branchText;
  if (dirText && branchText) {
    pathBranch = `${dirText}:${branchText}`;
  } else if (dirText) {
    pathBranch = dirText;
  }

  return {
    modeLabel,
    chip: chipText,
    provider,
    dir: rawDir,
    dirText,
    branch: cleanBranch,
    branchText,
    pathBranch,
    tokenCount,
    tokenUsage,
    maxTokens,
    gauge,
    showGauge,
    scopeLabel,
  };
}
