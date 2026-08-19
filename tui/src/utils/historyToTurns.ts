import type { ConversationTurn } from '../hooks/useConversation';
import { mapRawEvent } from '../services/transport/rawEventMapper';
import type { ScenarioEvent, ScenarioMode } from '../types/scenario';

/**
 * Converts backend session-history messages (chronological) into conversation
 * turns for the TUI, pairing each assistant message with the most recent user
 * turn that has not yet received a response.
 *
 * Handles non-alternating history (e.g. `user, user, assistant, assistant`)
 * without dropping or overwriting messages: events are always appended, never
 * replaced, and persisted events are preserved via the shared raw-event mapper.
 */
export function convertHistoryToTurns(
  messages: Record<string, unknown>[],
  defaultMode: ScenarioMode,
): ConversationTurn[] {
  const turns: ConversationTurn[] = [];
  let lastUnansweredUserTurn = -1;

  for (const msg of messages) {
    if (msg.role === 'user') {
      turns.push(createTurnFromUserMessage(msg, defaultMode));
      lastUnansweredUserTurn = turns.length - 1;
    } else if (msg.role === 'assistant') {
      const events = buildEventsFromAssistantMessage(msg);
      if (events.length === 0) continue;
      const targetIndex = lastUnansweredUserTurn >= 0 ? lastUnansweredUserTurn : turns.length - 1;
      if (targetIndex < 0) continue;
      turns[targetIndex].events.push(...events);
      lastUnansweredUserTurn = -1;
    }
  }
  return turns;
}

function createTurnFromUserMessage(msg: Record<string, unknown>, defaultMode: ScenarioMode): ConversationTurn {
  const mode = ((msg.metadata as Record<string, unknown>)?.mode as ScenarioMode) || defaultMode;
  const created = msg.created_at ? String(msg.created_at) : undefined;
  return {
    id: `hist_${msg.id}`,
    prompt: String(msg.content || ''),
    mode,
    model: (msg.metadata as Record<string, unknown>)?.model as string | undefined,
    events: [],
    isComplete: true,
    timestamp: created
      ? new Date(created).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false })
      : '??:??',
    timestampLong: created
      ? `${new Date(created).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false })}, ${new Date(created).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })}`
      : '??:??',
    startedAt: created ? new Date(created).getTime() : Date.now(),
  };
}

function buildEventsFromAssistantMessage(msg: Record<string, unknown>): ScenarioEvent[] {
  const rawEvents = Array.isArray(msg.events) ? (msg.events as Record<string, unknown>[]) : [];
  const events = rawEvents
    .filter((ev): ev is Record<string, unknown> => Boolean(ev && typeof ev === 'object' && ev.kind))
    .map((ev) => mapRawEvent(String(ev.kind), (ev.data as Record<string, unknown>) || {}, String(ev.id)));

  if (events.length === 0) {
    if (msg.content) {
      events.push({
        kind: 'message',
        id: `evt_hist_msg_${msg.id}`,
        text: String(msg.content),
        partial: false,
      } as ScenarioEvent);
    }
    events.push({
      kind: 'success',
      id: `evt_hist_ok_${msg.id}`,
      message: 'done',
    } as ScenarioEvent);
  }
  return events;
}
