/**
 * Tests the session resume data flow against the REAL production conversion:
 * convertHistoryToTurns (tui/src/utils/historyToTurns.ts), which App.tsx
 * handleSessionResume uses to restore history from backend messages.
 */
import { describe, test, expect } from 'vitest';
import { convertHistoryToTurns } from '../src/utils/historyToTurns';
import type { ScenarioEvent } from '../src/types/scenario';

function makeUserMsg(id: string, content: string, extra: Record<string, unknown> = {}): Record<string, unknown> {
  return { id, role: 'user', content, metadata: {}, created_at: new Date().toISOString(), ...extra };
}

function makeAssistantMsg(
  id: string,
  content: string,
  events: unknown[] = [],
): Record<string, unknown> {
  return { id, role: 'assistant', content, metadata: {}, created_at: new Date().toISOString(), events };
}

const mode = 'build' as const;

describe('convertHistoryToTurns (production conversion)', () => {
  test('normal alternating conversation produces one turn per user message', () => {
    const messages = [
      makeUserMsg('u1', 'My name is Alice'),
      makeAssistantMsg('a1', 'Hello Alice!'),
      makeUserMsg('u2', 'I like blue'),
      makeAssistantMsg('a2', 'Nice!'),
      makeUserMsg('u3', 'Dark theme please'),
      makeAssistantMsg('a3', 'Got it!'),
    ];
    const turns = convertHistoryToTurns(messages, mode);
    expect(turns).toHaveLength(3);
    expect(turns[0].prompt).toBe('My name is Alice');
    expect(turns[0].mode).toBe(mode);
    expect(turns[0].isComplete).toBe(true);
    expect(turns[0].events).toHaveLength(2);
    expect(turns[1].events).toHaveLength(2);
    expect(turns[2].events).toHaveLength(2);
  });

  test('non-alternating user,assistant,user,user,assistant,assistant preserves every message', () => {
    const messages = [
      makeUserMsg('u1', 'Hello'),
      makeAssistantMsg('a1', 'Hi!'),
      makeUserMsg('u2', 'Bye'),
      makeUserMsg('u3', 'Wait'),
      makeAssistantMsg('a2', 'OK!'),
      makeAssistantMsg('a3', 'Follow-up'),
    ];
    const turns = convertHistoryToTurns(messages, mode);
    expect(turns).toHaveLength(3);
    expect(turns.map((t) => t.prompt)).toEqual(['Hello', 'Bye', 'Wait']);
    expect(turns[0].events.map((e) => e.id)).toEqual(['evt_hist_msg_a1', 'evt_hist_ok_a1']);
    expect(turns[1].events).toHaveLength(0);
    // Both assistant messages attach to the same unanswered user turn.
    expect(turns[2].events.map((e) => e.id)).toEqual([
      'evt_hist_msg_a2',
      'evt_hist_ok_a2',
      'evt_hist_msg_a3',
      'evt_hist_ok_a3',
    ]);
  });

  test('consecutive user messages keep both prompts, response goes to the latest', () => {
    const messages = [
      makeUserMsg('u1', 'First'),
      makeUserMsg('u2', 'Second'),
      makeAssistantMsg('a1', 'Answering second'),
    ];
    const turns = convertHistoryToTurns(messages, mode);
    expect(turns).toHaveLength(2);
    expect(turns[0].prompt).toBe('First');
    expect(turns[1].prompt).toBe('Second');
    expect(turns[0].events).toHaveLength(0);
    expect(turns[1].events).toHaveLength(2);
    expect(turns[1].events[0].kind).toBe('message');
    expect((turns[1].events[0] as ScenarioEvent & { text: string }).text).toBe('Answering second');
  });

  test('consecutive assistant messages append, never overwrite earlier events', () => {
    const messages = [
      makeUserMsg('u1', 'Question'),
      makeAssistantMsg('a1', 'First answer'),
      makeAssistantMsg('a2', 'Second answer'),
    ];
    const turns = convertHistoryToTurns(messages, mode);
    expect(turns).toHaveLength(1);
    const ids = turns[0].events.map((e) => e.id);
    expect(ids).toEqual(['evt_hist_msg_a1', 'evt_hist_ok_a1', 'evt_hist_msg_a2', 'evt_hist_ok_a2']);
    const texts = turns[0].events
      .filter((e) => e.kind === 'message')
      .map((e) => (e as ScenarioEvent & { text: string }).text);
    expect(texts).toEqual(['First answer', 'Second answer']);
  });

  test('persisted events are preserved and mapped via the shared raw mapper', () => {
    const persisted = [
      { kind: 'thinking', id: 'evt_t1', data: { text: 'reasoning...' } },
      { kind: 'tool_call', id: 'evt_tc1', data: { tool: 'file_read', params: { path: 'a.txt' } } },
      { kind: 'success', id: 'evt_ok1', data: { message: 'Completed' } },
    ];
    const messages = [makeUserMsg('u1', 'Do it'), makeAssistantMsg('a1', 'Done', persisted)];
    const turns = convertHistoryToTurns(messages, mode);
    expect(turns).toHaveLength(1);
    const evs = turns[0].events;
    expect(evs).toHaveLength(3);
    expect(evs[0]).toMatchObject({ kind: 'thinking', id: 'evt_t1' });
    expect(evs[1]).toMatchObject({ kind: 'tool_call', id: 'evt_tc1', tool: 'file_read' });
    expect(evs[2]).toMatchObject({ kind: 'success', id: 'evt_ok1' });
  });

  test('empty or assistant-only input yields no turns', () => {
    expect(convertHistoryToTurns([], mode)).toHaveLength(0);
    expect(convertHistoryToTurns([makeAssistantMsg('a1', 'orphan')], mode)).toHaveLength(0);
  });

  test('metadata mode is honored per message with default fallback', () => {
    const messages = [
      makeUserMsg('u1', 'Plan something', { metadata: { mode: 'plan' } }),
      makeAssistantMsg('a1', 'Planned'),
    ];
    const turns = convertHistoryToTurns(messages, mode);
    expect(turns[0].mode).toBe('plan');
  });
});
