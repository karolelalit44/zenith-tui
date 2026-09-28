import { afterEach, describe, expect, it, vi } from 'vitest';
import { backendScenarioProvider } from '../src/services/transport/BackendScenarioProvider';
import { wsClient } from '../src/services/transport/WebSocketClient';
import type { ScenarioEvent } from '../src/types/scenario';

let rpcIdCounter = 0;
function makeRpcEvent(kind: string, data: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    jsonrpc: '2.0',
    method: 'event',
    params: {
      kind,
      id: `evt_repro_${++rpcIdCounter}`,
      data,
    },
  };
}

const emit = (kind: string, data: Record<string, unknown> = {}) =>
  (wsClient as unknown as { emitter: { emit: (name: string, data: unknown) => void } }).emitter.emit(
    'event',
    makeRpcEvent(kind, data),
  );

/**
 * Reproduces the real wire sequence from the Pydantic-v2 changelog turn
 * (session 0f3b1806): iteration 1 streams a degenerate/whitespace message
 * partial that is NEVER closed by a non-partial message event (the turn moved
 * on to tool calls). The final answer then arrives one iteration later.
 *
 * Regression guard: the final summary message must be emitted AFTER the tool
 * steps — its index must not reuse the stale partial-message index that was
 * opened before the first tool call.
 */
describe('BackendScenarioProvider message stream vs non-message interleave', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('does not reuse an early partial-message index for the final message after tool steps', () => {
    const received: Array<{ event: ScenarioEvent; index: number }> = [];
    let completed = false;

    const scenario = backendScenarioProvider.resolve('Find changelog', 'build');
    const runner = backendScenarioProvider.execute(
      scenario,
      (evt, idx) => {
        received.push({ event: evt, index: idx });
      },
      () => {
        completed = true;
      },
    );

    // Iteration 1: thinking, then a degenerate/whitespace message partial that
    // is never closed (stream continues into tool execution), then the tool.
    emit('thinking', { text: 'The user is asking me to: 1. Find the changelog', partial: true });
    emit('thinking', { text: 'The user is asking me to: 1. Find the changelog', duration: 2000, partial: false });
    emit('message', { text: ' ', partial: true });
    emit('progress', { percent: 0, label: 'Running websearch', iteration: 1, steps: [] });
    emit('tool_call', { tool: 'websearch', params: { query: 'Pydantic v2 changelog', max_results: 10 } });
    emit('tool_result', { tool: 'websearch', success: true, output: 'Search results...' });
    emit('progress', { percent: 100, label: 'Running websearch', iteration: 1, steps: [] });

    // Iteration 2: thinking + second tool.
    emit('thinking', { text: 'The search results show several relevant URLs.', partial: true });
    emit('thinking', { text: 'The search results show several relevant URLs.', duration: 1750, partial: false });
    emit('progress', { percent: 50, label: 'Running webfetch', iteration: 2, steps: [] });
    emit('tool_call', { tool: 'webfetch', params: { url: 'ref_doc_9', pattern: 'breaking changes' } });
    emit('tool_result', { tool: 'webfetch', success: true, output: 'Found 3 matches across 3745 lines' });
    emit('progress', { percent: 100, label: 'Running webfetch', iteration: 2, steps: [] });

    // Iteration 3: reasoning-only continuation, streams a stray partial message.
    emit('thinking', { text: 'The search found 3 matches for "breaking changes".', partial: true });
    emit('thinking', { text: 'The search found 3 matches for "breaking changes".', duration: 29312, partial: false });
    emit('message', { text: '...', partial: true });

    // Iteration 4: thinking + the REAL final answer as partials + non-partial.
    emit('thinking', { text: 'The user asked me to: 1. Find the changelog 2. Summarize.', partial: true });
    emit('thinking', { text: 'The user asked me to: 1. Find the changelog 2. Summarize.', partial: true });
    emit('thinking', {
      text: 'The user asked me to: 1. Find the changelog 2. Summarize. Let me provide the final answer.',
      duration: 1952,
      partial: false,
    });
    emit('message', { text: '## Summary', partial: true });
    emit('message', { text: '## Summary\n\nThe Pydantic v2 changelog is live.', partial: true });
    emit('message', {
      text: '## Summary\n\nThe Pydantic v2 changelog is live.',
      partial: false,
      iteration: 4,
    });
    emit('turn_manifest', { completed: true, created: [], modified: [] });
    emit('success', { message: 'Turn finished', iterations: 4 });

    expect(completed).toBe(true);
    runner.abort();

    const messages = received.filter((r) => r.event.kind === 'message');
    const finalMessage = messages.find((r) => !(r.event as { partial?: boolean }).partial);
    expect(finalMessage).toBeDefined();

    const firstMessagePartialIndex = messages[0]?.index;
    const lastToolIndex = Math.max(
      ...received.filter((r) => r.event.kind === 'tool_call' || r.event.kind === 'tool_result').map((r) => r.index),
    );

    // The final answer must be positioned AFTER the last tool step, not at the
    // stale index captured before the first tool call.
    expect(finalMessage!.index).toBeGreaterThan(lastToolIndex);
    expect(finalMessage!.index).not.toBe(firstMessagePartialIndex);

    // Same guarantee at the transport-visible level: the emitted message
    // events' index hint must not collide with the pre-tool stream.
    const distinctMessageIndices = Array.from(new Set(messages.map((r) => r.index)));
    expect(Math.max(...distinctMessageIndices)).toBeGreaterThan(lastToolIndex);
  });

  it('flushes accumulated real partial text when a tool interrupts mid-message', () => {
    const received: Array<{ event: ScenarioEvent; index: number }> = [];

    const scenario = backendScenarioProvider.resolve('mid stream', 'build');
    const runner = backendScenarioProvider.execute(
      scenario,
      (evt, idx) => {
        received.push({ event: evt, index: idx });
      },
      () => {},
    );

    // A message starts streaming, then a tool call interrupts without a
    // non-partial close. Real accumulated text must not be silently dropped.
    emit('message', { text: 'Let me check the workspace.', partial: true });
    emit('message', { text: 'Let me check the workspace first.', partial: true });
    emit('tool_call', { tool: 'file_read', params: { path: 'notes.txt' } });
    emit('tool_result', { tool: 'file_read', success: true, output: 'notes' });
    emit('message', { text: 'Done.', partial: false });
    emit('success', { message: 'done', iterations: 1 });

    runner.abort();

    const messages = received.filter((r) => r.event.kind === 'message');
    const flushed = messages.find(
      (r) => !(r.event as { partial?: boolean }).partial && r.event.text.includes('workspace first'),
    );
    const finalMessage = messages.find((r) => r.event.text === 'Done.');

    // The interrupted text is preserved as its own block, at its original slot.
    expect(flushed).toBeDefined();
    // The later real message starts a FRESH index after the interrupted block.
    expect(finalMessage!.index).toBeGreaterThan(flushed!.index);
  });
});
