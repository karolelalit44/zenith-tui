import type { Scenario, ScenarioMode } from '../../types/scenario';
import { ScenarioRepository } from '../data/ScenarioRepository';

export const getScenarioForPrompt = (prompt: string, mode: ScenarioMode): Scenario => {
  return ScenarioRepository.getScenarioForPrompt(prompt, mode);
};
