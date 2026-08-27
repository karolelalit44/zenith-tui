import {
  getToolStepPrimaryParam,
  INTERRUPTED_TOOL_ERROR,
  REPEATABLE_READ_ONLY_TOOL_SET,
  TOOL_META_INTERRUPTED,
  TOOL_META_REPEAT_COUNT,
} from '../constants/toolDisplay';
import type { ProgressEvent, ScenarioEvent, ToolCallEvent, ToolResultEvent, ToolStepEvent } from '../types/scenario';

/** Labels shorter than this cannot reliably identify a duplicated command. */
const DUPLICATE_LABEL_MIN_DETAIL_CHARS = 8;
/** How much of a pending step's primary value must appear to call it a dupe. */
const DUPLICATE_LABEL_MATCH_CHARS = 24;

function stepFromCall(call: ToolCallEvent): ToolStepEvent {
  return {
    kind: 'tool_step',
    id: call.id,
    tool: call.tool,
    params: call.params,
    text: call.text,
    success: false,
    output: '',
    error: INTERRUPTED_TOOL_ERROR,
    metadata: { [TOOL_META_INTERRUPTED]: true },
    pending: false,
  };
}

/**
 * Fold persisted tool_call → tool_result pairs into ONE completed tool_step
 * each, mirroring what the live reducer already does. This is what kills the
 * duplicated `→ Run …` / `✓ Run …` rows in restored scrollback.
 *
 * Pairing rules:
 *  - a result consumes the OLDEST still-open call for the same tool (the agent
 *    loop is serial per tool, so FIFO front == the matching call);
 *  - a call that never got a result becomes an interrupted tool_step (visible,
 *    honest — not silently dropped);
 *  - a result without any open call becomes a standalone completed tool_step;
 *  - existing tool_step events pass through untouched.
 */
export function pairToolEvents(events: ScenarioEvent[]): ScenarioEvent[] {
  if (!events.some((e) => e.kind === 'tool_call' || e.kind === 'tool_result')) {
    return events;
  }
  const out: ScenarioEvent[] = [];
  const openCalls = new Map<string, ToolStepEvent[]>();

  for (const ev of events) {
    if (ev.kind === 'tool_call') {
      const skeleton = stepFromCall(ev);
      const queue = openCalls.get(ev.tool) ?? [];
      queue.push(skeleton);
      openCalls.set(ev.tool, queue);
      out.push(skeleton);
      continue;
    }
    if (ev.kind === 'tool_result') {
      const res = ev as ToolResultEvent;
      const queue = openCalls.get(res.tool);
      const skeleton = queue && queue.length > 0 ? queue.shift() : undefined;
      if (skeleton) {
        skeleton.success = res.success;
        skeleton.output = res.output;
        skeleton.error = res.error;
        skeleton.truncated = res.truncated;
        skeleton.metadata = res.metadata;
      } else {
        out.push({
          kind: 'tool_step',
          id: res.id,
          tool: res.tool,
          params: {},
          success: res.success,
          output: res.output,
          error: res.error,
          truncated: res.truncated,
          metadata: res.metadata,
          pending: false,
        });
      }
      continue;
    }
    out.push(ev);
  }
  return out;
}

/**
 * Collapse CONSECUTIVE identical read-only invocations (same tool, same
 * primary argument) into one row carrying a repeat count. Nothing is hidden:
 * the row states how many times it ran. Non-adjacent repeats stay separate.
 */
export function foldReadOnlyRepeats(events: ScenarioEvent[]): ScenarioEvent[] {
  const out: ScenarioEvent[] = [];
  for (const ev of events) {
    const prev = out.length > 0 ? out[out.length - 1] : undefined;
    if (
      prev &&
      prev.kind === 'tool_step' &&
      ev.kind === 'tool_step' &&
      prev.tool === ev.tool &&
      REPEATABLE_READ_ONLY_TOOL_SET.has(prev.tool.toLowerCase()) &&
      getToolStepPrimaryParam(prev.tool, prev.params)?.value === getToolStepPrimaryParam(ev.tool, ev.params)?.value &&
      prev.success !== false &&
      ev.success !== false
    ) {
      const meta = { ...(prev.metadata ?? {}) };
      const currentCount =
        typeof meta[TOOL_META_REPEAT_COUNT] === 'number' ? (meta[TOOL_META_REPEAT_COUNT] as number) : 1;
      meta[TOOL_META_REPEAT_COUNT] = currentCount + 1;
      prev.metadata = meta;
      continue;
    }
    out.push(ev);
  }
  return out;
}
/**
 * True when a live progress row merely echoes a tool execution that already
 * renders as its own pending timeline card (same command/path snippet).
 *
 * Backend progress labels are `<activity>: <detail>` where detail is the
 * tool's primary param (command, path, pattern). If that snippet appears on
 * a pending ToolStepCard, the row is redundant. Phase-only rows ("summarizing
 * 42 KB of output") carry new information and are never suppressed.
 */
export function progressDuplicatesPendingToolStep(progress: ProgressEvent, turnEvents: ScenarioEvent[]): boolean {
  const active = progress.steps.find((s) => s.status === 'active') ?? progress.steps[progress.steps.length - 1];
  const label = (active?.label ?? progress.label) || '';
  if (!label) return false;
  for (const ev of turnEvents) {
    if (ev.kind !== 'tool_step' || !ev.pending) continue;
    const detail = getToolStepPrimaryParam(ev.tool, ev.params)?.value ?? '';
    if (
      typeof detail === 'string' &&
      detail.length >= DUPLICATE_LABEL_MIN_DETAIL_CHARS &&
      label.includes(detail.slice(0, DUPLICATE_LABEL_MATCH_CHARS))
    ) {
      return true;
    }
  }
  return false;
}
