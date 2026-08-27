import type { ScenarioMode } from '../types/scenario';
import { truncateEnd, truncateStart } from './text';
import { getWorkspaceFolderName } from './workspacePath';

export const FOOTER_EDGE_PAD = 4;
export const FOOTER_GAUGE_BLOCKS = 10;
const FOOTER_MIN_PROVIDER_LEN = 6;

export interface FooterLayoutInput {
  columns: number;
  mode: ScenarioMode;
  chip: string;
  providerName: string;
  dir: string;
  branch: string;
  /** Legacy cumulative count — used as the run-usage fallback when runTokens is omitted. */
  totalTokens?: number;
  effectiveMaxTokens?: number;
  /** Cumulative run/API token usage (telemetry). Preferred over totalTokens. */
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

  // Cumulative run/API telemetry — the footer count is run usage, never the
  // composed-context occupancy (which belongs in the gauge below). Labeled
  // explicitly so the two figures cannot be confused (P6.2).
  const runCount = typeof input.runTokens === 'number' ? input.runTokens : (input.totalTokens ?? 0);
  const hasRunUsage = runCount > 0 || typeof input.runTokens === 'number' || typeof input.totalTokens === 'number';
  const tokenUsage = hasRunUsage ? `RUN ${input.runEstimated === true ? '~' : ''}${formatRunTokens(runCount)} tok` : '';
  const tokenCount = tokenUsage;
  const maxTokens =
    typeof input.effectiveMaxTokens === 'number' && input.effectiveMaxTokens > 0 ? `${input.effectiveMaxTokens}` : '0';
  const scopeLabel = '';

  // Composed-context occupancy only — never mix cumulative run usage here.
  // Without an explicit contextPercent the footer renders no gauge at all.
  const gaugePercent =
    typeof input.contextPercent === 'number' ? Math.max(0, Math.min(100, Math.round(input.contextPercent))) : null;
  const filled = gaugePercent !== null ? Math.round((gaugePercent / 100) * FOOTER_GAUGE_BLOCKS) : 0;
  const gauge =
    gaugePercent !== null
      ? `[${'█'.repeat(filled)}${'░'.repeat(FOOTER_GAUGE_BLOCKS - filled)}] ${input.windowEstimated === true ? '~' : ''}CTX ${gaugePercent}%`
      : '';
  const showGauge = gauge !== '';

  const cleanBranch = input.branch ? input.branch.replace(/^\(+|\)+$/g, '').trim() : '';

  const rawDir = getWorkspaceFolderName(input.dir);

  const rightText = [gauge, tokenUsage].filter(Boolean).join(' ');
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
