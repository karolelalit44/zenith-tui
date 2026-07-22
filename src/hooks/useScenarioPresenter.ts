import { useMemo } from 'react';
import { ScenarioRepository } from '../services/data/ScenarioRepository';
import { StaticContentRepository } from '../services/data/StaticContentRepository';
import { ScenarioMode } from '../types/scenario';

export function useScenarioPresenter() {
  const uiContent = useMemo(() => StaticContentRepository.getUIContent(), []);

  const resolveScenario = (prompt: string, mode: ScenarioMode) => {
    return ScenarioRepository.getScenarioForPrompt(prompt, mode);
  };

  return {
    uiContent,
    resolveScenario,
  };
}
