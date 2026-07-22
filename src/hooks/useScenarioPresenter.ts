import { useMemo } from 'react';
import { getScenarioForPrompt } from '../services/data/ScenarioRepository';
import { getUIContent } from '../services/data/StaticContentRepository';
import { ScenarioMode } from '../types/scenario';

export function useScenarioPresenter() {
  const uiContent = useMemo(() => getUIContent(), []);

  const resolveScenario = (prompt: string, mode: ScenarioMode) => {
    return getScenarioForPrompt(prompt, mode);
  };

  return {
    uiContent,
    resolveScenario,
  };
}
