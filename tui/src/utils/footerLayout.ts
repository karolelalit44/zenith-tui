import { FOOTER_EDGE_PAD } from '../constants/layout';
import type { ScenarioMode } from '../types/scenario';
import { truncateEnd, truncateMiddle, truncateStart } from './text';
import { getWorkspaceFolderName } from './workspacePath';

const FOOTER_MIN_PROVIDER_LEN = 6;
const FOOTER_MIN_CHIP_LEN = 4;

export interface FooterLayoutInput {
  columns: number;
  mode: ScenarioMode;
  chip: string;
  providerName: string;
  dir: string;
  branch: string;
  /** Cumulative run/API token usage (telemetry). */
  runTokens?: number;
  /** Composed-context occupancy percent (0–100). Omitted → no context segment renders. */
  contextPercent?: number;
  /** Whether Calm Mode is active. */
  calmMode?: boolean;
}

export interface FooterLayoutOutput {
  modeLabel: string;
  chip: string;
  provider: string;
  dir: string;
  dirText: string;
  branch: string;
  branchText: string;
  calmLabel: string;
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
  const contentWidth = Math.max(1, columns - FOOTER_EDGE_PAD);
  const modeLabel =
    contentWidth < 14 ? (input.mode === 'plan' ? 'P ' : 'B ') : input.mode === 'plan' ? '[PLAN] ' : '[BUILD] ';

  const gaugePercent =
    typeof input.contextPercent === 'number' ? Math.max(0, Math.min(100, input.contextPercent)) : null;

  // Token telemetry uses bare figures with no `tok`/`ctx` labels: run usage is
  // shown when runTokens is a defined number (even 0), while context occupancy
  // remains independent of that counter.
  const runCount = typeof input.runTokens === 'number' ? input.runTokens : 0;
  const hasRunUsage = typeof input.runTokens === 'number';
  const tokenStr = hasRunUsage ? formatRunTokens(runCount) : '';
  const ctxStr = gaugePercent !== null ? `${gaugePercent.toFixed(1)}%` : '';
  let tokenUsage = [tokenStr, ctxStr].filter(Boolean).join(' · ');
  let calmLabel = input.calmMode ? '⟪CALM⟫' : '';

  const cleanBranch = input.branch ? input.branch.replace(/^\(+|\)+$/g, '').trim() : '';
  const rawDir = getWorkspaceFolderName(input.dir);

  const chipPrefixWidth = input.chip ? 2 : 0; // "◇ "
  const fixedLeft = modeLabel.length + chipPrefixWidth;
  let available = Math.max(0, contentWidth - fixedLeft);

  const minChipWidth = Math.min(input.chip.length, FOOTER_MIN_CHIP_LEN);
  if (tokenUsage && available - (tokenUsage.length + 1) >= minChipWidth) {
    available -= tokenUsage.length + 1;
  } else {
    tokenUsage = '';
  }

  if (calmLabel && available - (calmLabel.length + 1) >= minChipWidth) {
    available -= calmLabel.length + 1;
  } else {
    calmLabel = '';
  }

  // Model chip gets first claim on the remaining width and truncates from the
  // middle so the unique tail (e.g. "-550b-a55b") is never silently dropped.
  // Clamped to `available` as well: `minChipWidth` is a legibility floor, not a
  // licence to overrun the terminal — below ~14 columns the floor exceeds the
  // whole budget and the footer would overflow its own width.
  const chipBudget = Math.min(
    input.chip.length,
    Math.min(available, Math.max(minChipWidth, Math.floor(available * 0.35))),
  );
  const chipText = truncateMiddle(input.chip, Math.max(0, chipBudget));
  available -= chipText.length;

  let provider = '';
  if (available >= FOOTER_MIN_PROVIDER_LEN && input.providerName) {
    const name = truncateEnd(input.providerName, Math.max(0, available - 3));
    provider = ` · ${name}`;
    available -= provider.length;
  }

  let branchText = '';
  let dirText = '';
  if (available > 0) {
    if (rawDir && cleanBranch && available >= 4) {
      const pathBudget = available - 2; // colon plus trailing branch spacer
      const branchBudget = Math.max(1, Math.min(cleanBranch.length, Math.floor(pathBudget * 0.45)));
      branchText = truncateEnd(cleanBranch, branchBudget);
      const dirBudget = Math.max(0, pathBudget - branchText.length);
      dirText = truncateStart(rawDir, dirBudget);
    } else if (cleanBranch && available >= 2) {
      branchText = truncateEnd(cleanBranch, available - 1);
    } else if (rawDir) {
      dirText = truncateStart(rawDir, available);
    }
  }

  return {
    modeLabel,
    chip: chipText,
    provider,
    dir: rawDir,
    dirText,
    branch: cleanBranch,
    branchText,
    calmLabel,
    tokenUsage,
  };
}
