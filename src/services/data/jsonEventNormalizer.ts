import type { ScenarioEvent } from '../../types/scenario';

export function parseJsonEvent(evt: ScenarioEvent | string | Record<string, unknown>): ScenarioEvent {
  if (typeof evt === 'string') {
    try {
      const parsed = JSON.parse(evt);
      return {
        id: parsed.id || `evt_${parsed.kind || 'msg'}`,
        kind: parsed.kind || 'message',
        ...parsed,
      };
    } catch (_e) {
      return {
        id: `evt_raw_msg`,
        kind: 'message',
        text: evt,
      } as ScenarioEvent;
    }
  }

  // If already a scenario event object, return directly without mutating or generating new keys
  if (typeof evt === 'object' && evt !== null && 'kind' in evt) {
    const rawObj = evt as Record<string, unknown>;
    if (!rawObj.id) {
      rawObj.id = `evt_${rawObj.kind}`;
    }
    return rawObj as unknown as ScenarioEvent;
  }

  return evt as unknown as ScenarioEvent;
}
