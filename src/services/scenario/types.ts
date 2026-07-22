import type { Scenario, ScenarioEvent, ScenarioMode } from '../../types/scenario';

export type ScenarioListener = (event: ScenarioEvent, index: number) => void;

export interface ScenarioRunner {
  abort: () => void;
}

export interface ScenarioProvider {
  readonly name: string;
  resolve(prompt: string, mode: ScenarioMode): Scenario;
  execute(scenario: Scenario, onEvent: ScenarioListener, onComplete: () => void): ScenarioRunner;
}
