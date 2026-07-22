import type { Scenario, ScenarioMode } from '../../../types/scenario';
import { getScenarioForPrompt } from '../../data/ScenarioRepository';
import { runScenario } from '../engine';
import type { ScenarioListener, ScenarioProvider, ScenarioRunner } from '../types';

export class MockScenarioProvider implements ScenarioProvider {
  readonly name = 'mock';

  resolve(prompt: string, mode: ScenarioMode): Scenario {
    return getScenarioForPrompt(prompt, mode);
  }

  execute(scenario: Scenario, onEvent: ScenarioListener, onComplete: () => void): ScenarioRunner {
    return runScenario(scenario, onEvent, onComplete);
  }
}
