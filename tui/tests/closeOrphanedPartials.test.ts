import { describe, expect, it } from 'vitest';
import { closeOrphanedPartialThinking } from '../src/hooks/useConversation';
import { backendScenarioProvider } from '../src/services/transport/BackendScenarioProvider';
import { type JsonRpcEvent, wsClient } from '../src/services/transport/WebSocketClient';
import type { MessageEvent, ScenarioEvent, ThinkingEvent } from '../src/types/scenario';
import { upsertEvent } from '../src/utils/eventUpsert';

let rpcIdCounter = 500000;
function makeRpcEvent(kind: string, data: Record<string, unknown> = {}): JsonRpcEvent {
  return {
    jsonrpc: '2.0',
    method: 'event',
    params: { kind, id: `orphan_${++rpcIdCounter}`, data },
  };
}

describe('closeOrphanedPartialThinking', () => {
  it('closes an orphan partial thinking, preserving text and duration', () => {
    const orphan: ThinkingEvent = {
      kind: 'thinking',
      id: 'evt_orphan',
      thoughts: ['Partial reasoning text'],
      duration: 0,
      partial: true,
    };
    const msg: MessageEvent = { kind: 'message', id: 'evt_msg', text: 'hi', partial: false };
    const next = closeOrphanedPartialThinking([orphan, msg]);
    expect(next.length).toBe(2);
    const closed = next[0] as ThinkingEvent;
    expect(closed.partial).toBe(false);
    expect(closed.thoughts).toEqual(['Partial reasoning text']);
    expect(next[1]).toBe(msg);
  });

  it('returns the input untouched when nothing is orphaned', () => {
    const final: ThinkingEvent = {
      kind: 'thinking',
      id: 'evt_final',
      thoughts: ['Full reasoning'],
      duration: 4000,
      partial: false,
    };
    const events: ScenarioEvent[] = [final];
    expect(closeOrphanedPartialThinking(events)).toBe(events);
    expect(closeOrphanedPartialThinking([])).toEqual([]);
  });

  it('abort mid-reasoning freezes the partial as ONE static Thought (no truncated duplicate)', () => {
    // Same routing as useScenario: partials batch, non-partials flush+upsert.
    let state: ScenarioEvent[] = [];
    const queue: Array<{ event: ScenarioEvent; index: number }> = [];
    const flush = () => {
      for (const { event, index } of queue.splice(0)) {
        state = upsertEvent(state, event, index);
      }
    };
    const onEvent = (event: ScenarioEvent, index: number) => {
      const isPartial =
        (event.kind === 'message' && (event as { partial?: boolean }).partial === true) ||
        (event.kind === 'thinking' && (event as ThinkingEvent).partial === true);
      if (isPartial) queue.push({ event, index });
      else {
        flush();
        state = upsertEvent(state, event, index);
      }
    };

    const scenario = backendScenarioProvider.resolve('test', 'build');
    const runner = backendScenarioProvider.execute(scenario, onEvent, () => {});
    const emit = (kind: string, data: Record<string, unknown> = {}) =>
      (wsClient as unknown as { emitter: { emit: (n: string, d: unknown) => void } }).emitter.emit(
        'event',
        makeRpcEvent(kind, data),
      );

    // ESC during reasoning: partial arrives, final never does.
    emit('thinking', { text: 'Partial reasoning text cut off', partial: true });
    runner.abort();
    flush();

    const closed = closeOrphanedPartialThinking(state);
    const thoughts = closed.filter((e): e is ThinkingEvent => e.kind === 'thinking');
    expect(thoughts.length).toBe(1);
    expect(thoughts[0].partial).toBe(false);
    expect(thoughts[0].thoughts.join(' ')).toContain('cut off');
  });
});
