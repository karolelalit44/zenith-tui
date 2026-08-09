import { formatTokenCount } from '../services/api/tokenEstimationService';
import type { ScenarioMode } from '../types/scenario';
import { truncateEnd } from './text';

export const FOOTER_EDGE_PAD = 4;
export const FOOTER_MIN_CHIP_LEN = 8;
export const FOOTER_GAUGE_BLOCKS = 10;
const FOOTER_MIN_PROVIDER_LEN = 6;
const FOOTER_MIN_BRANCH_LEN = 5;

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
  branch: string;
  tokenCount: string;
  maxTokens: string;
  gauge: string;
  status: string;
  showGauge: boolean;
  scopeLabel: string;
}

export function computeFooterLayout(input: FooterLayoutInput): FooterLayoutOutput {
  const contentWidth = Math.max(24, input.columns - FOOTER_EDGE_PAD);
  const modeLabel = input.mode === 'plan' ? '[PLAN] ' : '[BUILD] ';

  const tokenCount = formatTokenCount(input.totalTokens);
  const maxTokens = formatTokenCount(input.effectiveMaxTokens);
  const scopeLabel = input.tokenScope === 'turn' ? ' (turn)' : input.tokenScope === 'session' ? ' (session)' : '';

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

  const leftFixed = modeLabel.length + 4;
  const coreFixed = 3 + tokenCount.length + 1 + maxTokens.length + 8 + 3 + status.length + scopeLabel.length;

  let showGauge = true;
  let rightFixed = coreFixed + gauge.length;
  let available = contentWidth - leftFixed - rightFixed;

  if (available < FOOTER_MIN_CHIP_LEN) {
    showGauge = false;
    rightFixed = coreFixed;
    available = contentWidth - leftFixed - rightFixed;
  }

  const chipBudget = Math.max(0, available);
  const chipText = truncateEnd(input.chip, chipBudget);
  let remaining = Math.max(0, available - chipText.length);

  let provider = '';
  if (remaining >= FOOTER_MIN_PROVIDER_LEN && input.providerName) {
    const name = truncateEnd(input.providerName, remaining - 3);
    provider = ` · ${name}`;
    remaining = Math.max(0, remaining - provider.length);
  }

  let branchText = '';
  if (remaining >= FOOTER_MIN_BRANCH_LEN && input.branch) {
    const inner = truncateEnd(input.branch, Math.max(1, remaining - 3));
    branchText = ` (${inner})`;
    remaining = Math.max(0, remaining - branchText.length);
  }

  let dirText = '';
  if (remaining >= 1 && input.dir) {
    dirText = truncateEnd(input.dir, remaining);
  }

  return {
    modeLabel,
    chip: chipText,
    provider,
    dir: dirText,
    branch: branchText,
    tokenCount,
    maxTokens,
    gauge,
    status,
    showGauge,
    scopeLabel,
  };
}
