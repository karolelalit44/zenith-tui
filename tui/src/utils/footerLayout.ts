import { FOOTER_EDGE_PAD } from '../constants/layout';
import type { ScenarioMode } from '../types/scenario';
import { truncateEnd, truncateMiddle, truncateStart } from './text';
import { getWorkspaceFolderName } from './workspacePath';

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
  /** Composed-context occupancy percent (0–100). Omitted → no ctx segment renders. */
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
  tokenUsage: string;
}

/** Compact cumulative run/API token telemetry (e.g. 12.4K, 1.2M, 420). */
export function formatRunTokens(count: number): string {
  if (count <= 0) return '0';
  if (count >= 1_000_000) return `${(count / 1_000_000).toFixed(1)}M`;
  if (count >= 1_000) return `${(count / 1_000).toFixed(1)}K`;
  return String(count);
}

export function computeFooterLayout(input: FooterLayoutInput): FooterLayoutOutput {
  const columns = input.columns || 80;
  const contentWidth = Math.max(24, columns - FOOTER_EDGE_PAD);
  const modeLabel = input.mode === 'plan' ? '[PLAN] ' : '[BUILD] ';

  const gaugePercent =
    typeof input.contextPercent === 'number' ? Math.max(0, Math.min(100, input.contextPercent)) : null;

  // Token telemetry: always shown when runTokens is a defined number (even 0),
  // and the ctx occupancy is independent of the token counter — a live run with
  // 0 accumulated tokens must still report its context fill.
  const runCount = typeof input.runTokens === 'number' ? input.runTokens : 0;
  const hasRunUsage = typeof input.runTokens === 'number';
  const tokenStr = hasRunUsage ? `${formatRunTokens(runCount)} tok` : '';
  const ctxStr = gaugePercent !== null ? `${gaugePercent.toFixed(1)}% ctx` : '';
  const tokenUsage = [tokenStr, ctxStr].filter(Boolean).join(' · ');

  const cleanBranch = input.branch ? input.branch.replace(/^\(+|\)+$/g, '').trim() : '';
  const rawDir = getWorkspaceFolderName(input.dir);

  const rightText = tokenUsage;
  const tokenWidth = rightText.length + (rightText ? 1 : 0);
  const colonWidth = rawDir && cleanBranch ? 1 : 0;
  const fixedRight = tokenWidth + colonWidth + 1;
  const fixedLeft = modeLabel.length + 3; // mode + "◇ "

  let available = contentWidth - fixedLeft - fixedRight;

  // Model chip gets first claim on the remaining width and truncates from the
  // middle so the unique tail (e.g. "-550b-a55b") is never silently dropped.
  const chipBudget = Math.max(6, Math.min(input.chip.length, Math.floor(available * 0.35)));
  const chipText = truncateMiddle(input.chip, chipBudget);
  available -= chipText.length;

  let provider = '';
  if (available >= FOOTER_MIN_PROVIDER_LEN && input.providerName) {
    const name = truncateEnd(input.providerName, available - 3);
    provider = ` · ${name}`;
    available -= provider.length;
  }

  const branchBudget = Math.max(1, Math.min(cleanBranch.length, Math.max(1, Math.floor(available * 0.45))));
  const branchText = truncateEnd(cleanBranch, branchBudget);
  available = Math.max(0, available - branchText.length);

  const dirBudget = Math.max(1, available);
  const dirText = truncateStart(rawDir, dirBudget);

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
    tokenUsage,
  };
}
