import { useState, useCallback, useRef } from 'react';
import { ScenarioEvent, ScenarioMode } from '../types/scenario';
import { runScenario, getScenarioForPrompt, ScenarioRunner } from '../services/scenario';

export function useScenario() {
  const [events, setEvents] = useState<ScenarioEvent[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [currentPrompt, setCurrentPrompt] = useState('');
  const [mode, setMode] = useState<ScenarioMode | null>(null);
  const runnerRef = useRef<ScenarioRunner | null>(null);

  const startScenario = useCallback((prompt: string, selectedMode: ScenarioMode) => {
    setMode(selectedMode);
    setCurrentPrompt(prompt);
    setEvents([]);
    setIsRunning(true);

    const scenario = getScenarioForPrompt(prompt, selectedMode);

    runnerRef.current = runScenario(
      scenario,
      (event) => {
        setEvents(prev => [...prev, event]);
      },
      () => {
        setIsRunning(false);
      }
    );
  }, []);

  const abort = useCallback(() => {
    runnerRef.current?.abort();
    setIsRunning(false);
  }, []);

  const reset = useCallback(() => {
    runnerRef.current?.abort();
    setEvents([]);
    setIsRunning(false);
    setCurrentPrompt('');
    setMode(null);
  }, []);

  return {
    events,
    isRunning,
    currentPrompt,
    mode,
    startScenario,
    abort,
    reset,
  };
}
