import type { ScenarioEvent } from '../types/scenario';

/**
 * Insert or replace an event by id (preferred), falling back to an index hint
 * when the id is unknown. Id-based patching is the stable contract for live
 * streaming updates (partial messages, merged thinking) and history replay.
 */
export function upsertEvent(events: ScenarioEvent[], event: ScenarioEvent, index?: number): ScenarioEvent[] {
  const existingIndex = events.findIndex((e) => Boolean(e.id) && e.id === event.id);
  if (existingIndex >= 0) {
    const next = [...events];
    next[existingIndex] = event;
    return next;
  }
  // Only replace by index if target slot is a transient placeholder (progress indicator)
  if (typeof index === 'number' && index >= 0 && index < events.length && events[index].kind === 'progress') {
    const next = [...events];
    next[index] = event;
    return next;
  }
  return [...events, event];
}

export interface PendingToolStep {
  callId?: string;
  index?: number;
  tool: string;
  params: Record<string, unknown>;
  text?: string;
}

/**
 * Pair a tool_result with its pending tool_call. The backend assigns every
 * event its own id, so an exact id match is the fast path; when it misses, fall
 * back to the earliest unresolved pending call of the same tool (tools execute
 * sequentially, so FIFO-by-tool is the correct ordering). The matched entry is
 * removed from the map. Returns null when no pending call matches (a true
 * orphan, e.g. history resumed mid-turn).
 */
export function resolvePendingToolStep(
  pending: Map<string, PendingToolStep>,
  id: string,
  tool: string,
): { key: string; step: PendingToolStep } | null {
  const exact = pending.get(id);
  if (exact) {
    pending.delete(id);
    return { key: id, step: exact };
  }
  for (const [key, step] of pending) {
    if (step.tool === tool) {
      pending.delete(key);
      return { key, step };
    }
  }
  return null;
}
