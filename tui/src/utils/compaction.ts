import type {
  CompactionPhase,
  CompactionStatus,
  CompactionTrigger,
  ContextCompactionFlowEvent,
  ContextPreservation,
  ScenarioEvent,
} from '../types/scenario';

const COMPACTION_KINDS = new Set([
  'context_compaction_started',
  'context_compaction_phase',
  'context_compacted',
  'context_compaction_ended',
]);

const MAX_NOTES = 3;

/**
 * Fold `context_compaction_started` / `context_compaction_phase` /
 * `context_compacted` / `context_compaction_ended` events into a single
 * `ContextCompactionFlowEvent` so the UI renders ONE continuous status card.
 * Returns `null` when no compaction events are present.
 *
 * Phase precedence:
 *   1. Explicit `context_compaction_phase` events (latest wins).
 *   2. Terminal event (`context_compaction_ended`) → `ready` / `failed`.
 *   3. Any tool-prune (`context_compacted`) → `compacting`.
 *   4. Otherwise `context_compaction_started` → `preparing`.
 */
export function consolidateCompactionEvents(events: ScenarioEvent[]): ContextCompactionFlowEvent | null {
  const present = events.filter((e) => COMPACTION_KINDS.has(e.kind));
  if (present.length === 0) return null;

  let sourceId = present[0].id;
  let phase: CompactionPhase = 'preparing';
  let hasPhaseEvent = false;
  let beforeTokens: number | undefined;
  let afterTokens: number | undefined;
  let totalTokens: number | undefined;
  let tokensSaved: number | undefined;
  let summaryChars: number | undefined;
  let preserved: ContextPreservation | undefined;
  let summary: string | undefined;
  let failed: boolean | undefined;
  let trigger: CompactionTrigger | undefined;
  let status: CompactionStatus | undefined;
  const notes: string[] = [];

  for (const evt of present) {
    if (evt.kind === 'context_compaction_started') {
      sourceId = evt.id;
      if (typeof evt.used === 'number' && beforeTokens === undefined) {
        beforeTokens = evt.used;
      }
      if (typeof evt.total === 'number' && totalTokens === undefined) {
        totalTokens = evt.total;
      }
      if (hasPhaseEvent === false) phase = 'preparing';
      if (evt.trigger && trigger === undefined) trigger = evt.trigger;
      if (evt.status) status = evt.status;
    } else if (evt.kind === 'context_compaction_phase') {
      hasPhaseEvent = true;
      sourceId = evt.id;
      phase = evt.phase;
      if (evt.phase === 'failed') failed = true;
      if (typeof evt.beforeTokens === 'number') beforeTokens = evt.beforeTokens;
      if (typeof evt.afterTokens === 'number') afterTokens = evt.afterTokens;
      if (evt.trigger && trigger === undefined) trigger = evt.trigger;
    } else if (evt.kind === 'context_compacted') {
      sourceId = evt.id;
      if (!hasPhaseEvent && phase === 'preparing') phase = 'compacting';
      if (notes.length < MAX_NOTES && evt.message) {
        const trimmedMsg = evt.message.trim();
        const note = trimmedMsg.toLowerCase().startsWith('compacted ') ? trimmedMsg.slice(10).trim() : trimmedMsg;
        if (note) notes.push(note);
      }
      if (typeof evt.tokensSaved === 'number') {
        tokensSaved = (tokensSaved ?? 0) + evt.tokensSaved;
      }
    } else if (evt.kind === 'context_compaction_ended') {
      sourceId = evt.id;
      phase = failed ? 'failed' : 'ready';
      if (typeof evt.used === 'number') afterTokens = evt.used;
      if (typeof evt.total === 'number') totalTokens = evt.total;
      if (typeof evt.tokensSaved === 'number') tokensSaved = evt.tokensSaved;
      if (typeof evt.summaryChars === 'number') summaryChars = evt.summaryChars;
      if (evt.preserved) preserved = evt.preserved;
      if (typeof evt.summary === 'string' && evt.summary.trim().length > 0) summary = evt.summary;
      if (evt.failed === true) {
        failed = true;
        phase = 'failed';
      }
      if (evt.trigger && trigger === undefined) trigger = evt.trigger;
      if (evt.status) status = evt.status;
    }
  }

  return {
    kind: 'context_compaction_flow',
    id: sourceId,
    phase,
    beforeTokens,
    afterTokens,
    totalTokens,
    tokensSaved,
    summaryChars,
    preserved,
    summary,
    notes,
    failed,
    trigger,
    status,
  };
}
