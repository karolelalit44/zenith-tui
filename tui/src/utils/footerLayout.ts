import type { ScenarioMode } from '../types/scenario';
import { truncateEnd, truncateStart } from './text';

export const FOOTER_EDGE_PAD = 4;
export const FOOTER_MIN_CHIP_LEN = 8;
export const FOOTER_GAUGE_BLOCKS = 10;
const FOOTER_MIN_PROVIDER_LEN = 6;

export interface FooterLayoutInput {
  columns: number;
  mode: ScenarioMode;
  chip: string;
  providerName: string;
  dir: string;
  branch: string;
  totalTokens: number;
  effectiveMaxTokens: number;
  running: boolean;
  disabled: boolean;
  inputEmpty: boolean;
  tokenScope?: 'turn' | 'session';
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
  status: string;
  showGauge: boolean;
  scopeLabel: string;
}

export function formatTokenUsage(totalTokens: number, maxTokens: number): string {
  let countStr = '0.0K';
  if (totalTokens >= 1_000_000) {
    countStr = `${(totalTokens / 1_000_000).toFixed(1)}M`;
  } else if (totalTokens >= 1_000) {
    countStr = `${(totalTokens / 1_000).toFixed(1)}K`;
  } else if (totalTokens > 0) {
    countStr = `${(totalTokens / 1000).toFixed(1)}K`;
  } else {
    countStr = '0.0K';
  }

  const pct = maxTokens > 0 ? Math.min(100, Math.round((totalTokens / maxTokens) * 100)) : 0;
  return `${countStr} (${pct}%)`;
}

export function computeFooterLayout(input: FooterLayoutInput): FooterLayoutOutput {
  const contentWidth = Math.max(24, input.columns - FOOTER_EDGE_PAD);
  const modeLabel = input.mode === 'plan' ? '[PLAN] ' : '[BUILD] ';

  const tokenUsage = formatTokenUsage(input.totalTokens, input.effectiveMaxTokens);
  const tokenCount = tokenUsage;
  const maxTokens = input.effectiveMaxTokens > 0 ? `${input.effectiveMaxTokens}` : '0';
  const scopeLabel = '';

  const percent =
    input.effectiveMaxTokens > 0 ? Math.min(100, Math.round((input.totalTokens / input.effectiveMaxTokens) * 100)) : 0;
  const filled = Math.max(0, Math.min(FOOTER_GAUGE_BLOCKS, Math.round((percent / 100) * FOOTER_GAUGE_BLOCKS)));
  const gauge = `[${'█'.repeat(filled)}${'░'.repeat(FOOTER_GAUGE_BLOCKS - filled)}] ${percent}%`;

  const status = input.running
    ? '\\ Esc cancel'
    : input.disabled
      ? 'Input disabled'
      : input.inputEmpty
        ? '↵'
        : '↵ send';

  const cleanBranch = input.branch ? input.branch.replace(/^\(+|\)+$/g, '').trim() : '';

  let rawDir = input.dir ? input.dir.replace(/\\/g, '/').split('/').filter(Boolean).pop() || '' : '';
  if (!rawDir) rawDir = input.dir || '';

  const runningWidth = input.running ? 11 : 0;
  const tokenWidth = tokenUsage.length + 1;
  const colonWidth = rawDir && cleanBranch ? 1 : 0;
  const fixedRight = runningWidth + tokenWidth + colonWidth + 1;
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
    status,
    showGauge: false,
    scopeLabel,
  };
}
