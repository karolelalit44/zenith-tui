import type { ConversationTurn } from '../hooks/useConversation';
import { mapRawEvent } from '../services/transport/rawEventMapper';
import type { FileAttachment, ScenarioEvent, ScenarioMode } from '../types/scenario';
import { pairToolEvents } from './pairToolEvents';

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
  const metadata = (msg.metadata as Record<string, unknown>) || {};
  const mode = (metadata?.mode as ScenarioMode) || defaultMode;
  const created = msg.created_at ? String(msg.created_at) : undefined;
  const attachments = metadata?.attachment_refs
    ? Array.isArray(metadata.attachment_refs)
      ? (metadata.attachment_refs as Record<string, unknown>[])
          .filter((a): a is Record<string, unknown> => Boolean(a && typeof a === 'object' && a.path))
          .map((a) => {
            const p = String(a.path);
            return {
              path: p,
              name: String(a.name ?? p.split('/').pop() ?? p),
              mimeType: a.kind === 'folder' ? 'inode/directory' : 'text/plain',
              size: typeof a.size === 'number' ? a.size : 0,
              kind: a.kind === 'folder' ? 'folder' : 'file',
            } as FileAttachment;
          })
      : undefined
    : undefined;
  return {
    id: `hist_${msg.id}`,
    prompt: String(msg.content || ''),
    mode,
    model: metadata?.model as string | undefined,
    events: [],
    isComplete: true,
    timestamp: created
      ? new Date(created).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false })
      : '??:??',
    timestampLong: created
      ? `${new Date(created).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false })}, ${new Date(created).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })}`
      : '??:??',
    startedAt: created ? new Date(created).getTime() : Date.now(),
    attachments,
  };
}

function buildEventsFromAssistantMessage(msg: Record<string, unknown>): ScenarioEvent[] {
  const rawEvents = Array.isArray(msg.events) ? (msg.events as Record<string, unknown>[]) : [];
  // Streaming partials are transient render state, never durable content: the
  // final non-partial MESSAGE event carries the full text. Replaying the
  // persisted partial chunks would duplicate every assistant message block.
  const hasCompletedThinking = rawEvents.some(
    (ev) => ev && typeof ev === 'object' && ev.kind === 'thinking' && !(ev.data as Record<string, unknown>)?.partial,
  );
  const events = rawEvents
    .filter((ev): ev is Record<string, unknown> => Boolean(ev && typeof ev === 'object' && ev.kind))
    .filter((ev) => !(ev.kind === 'message' && (ev.data as Record<string, unknown>)?.partial === true))
    .filter(
      (ev) =>
        !(hasCompletedThinking && ev.kind === 'thinking' && (ev.data as Record<string, unknown>)?.partial === true),
    )
    .map((ev) => mapRawEvent(String(ev.kind), (ev.data as Record<string, unknown>) || {}, String(ev.id)));

  // Persisted tool_call/tool_result pairs are folded into single tool_step
  // events here (same contract as the live reducer) so restored scrollback
  // renders ONE coherent execution row per tool instead of a duplicate
  // pending-style arrow row plus a separate result row.
  const paired = pairToolEvents(events);

  const hasMessage = paired.some(
    (e) => e.kind === 'message' && Boolean((e as import('../types/scenario').MessageEvent).text?.trim()),
  );
  if (!hasMessage && msg.content && String(msg.content).trim()) {
    const msgEvent: ScenarioEvent = {
      kind: 'message',
      id: `evt_hist_msg_${msg.id}`,
      text: String(msg.content),
      partial: false,
    };
    const terminalIdx = paired.findIndex((e) => e.kind === 'turn_manifest' || e.kind === 'success');
    if (terminalIdx >= 0) {
      paired.splice(terminalIdx, 0, msgEvent);
    } else {
      paired.push(msgEvent);
    }
  }

  return paired;
}
