import type { Scenario, ScenarioEvent, ScenarioMode } from '../../types/scenario';

let idCounter = 0;
const uid = () => `evt_${++idCounter}`;

export interface EventTemplate {
  kind: ScenarioEvent['kind'];
  [key: string]: unknown;
}

export interface ScenarioTemplate {
  mode: ScenarioMode;
  events: EventTemplate[];
}

function assignIds(events: EventTemplate[]): ScenarioEvent[] {
  return events.map((evt) => ({ ...evt, id: uid() })) as ScenarioEvent[];
}

export function createScenario(prompt: string, template: ScenarioTemplate): Scenario {
  return {
    id: `${template.mode}_${Date.now()}`,
    mode: template.mode,
    prompt,
    events: assignIds(template.events),
  };
}

export function resetIdCounter(): void {
  idCounter = 0;
}
