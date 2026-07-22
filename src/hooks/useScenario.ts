import { useCallback, useRef, useState } from 'react';
import { MockScenarioProvider } from '../services/scenario/providers/MockScenarioProvider';
import type { ScenarioProvider, ScenarioRunner } from '../services/scenario/types';
import type { ScenarioEvent, ScenarioMode } from '../types/scenario';

export interface UseScenarioReturn {
  events: ScenarioEvent[];
  isRunning: boolean;
  startScenario: (prompt: string, mode: ScenarioMode) => void;
  abort: () => void;
}

const createDefaultProvider = (): ScenarioProvider => new MockScenarioProvider();

let _cachedDefault: ScenarioProvider | null = null;
const getDefaultProvider = (): ScenarioProvider => {
  if (!_cachedDefault) _cachedDefault = createDefaultProvider();
  return _cachedDefault;
};

export function useScenario(provider?: ScenarioProvider): UseScenarioReturn {
  const resolvedProvider = provider ?? getDefaultProvider();
  const [events, setEvents] = useState<ScenarioEvent[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [_currentPrompt, setCurrentPrompt] = useState('');
  const [_mode, setMode] = useState<ScenarioMode | null>(null);
  const runnerRef = useRef<ScenarioRunner | null>(null);

  const startScenario = useCallback(
    (prompt: string, selectedMode: ScenarioMode) => {
      setMode(selectedMode);
      setCurrentPrompt(prompt);
      setEvents([]);
      setIsRunning(true);

      const scenario = resolvedProvider.resolve(prompt, selectedMode);

      runnerRef.current = resolvedProvider.execute(
        scenario,
        (event) => {
          setEvents((prev) => [...prev, event]);
        },
        () => {
          setIsRunning(false);
        },
      );
    },
    [resolvedProvider],
  );

  const abort = useCallback(() => {
    runnerRef.current?.abort();
    setIsRunning(false);
  }, []);

  const _reset = useCallback(() => {
    runnerRef.current?.abort();
    setEvents([]);
    setIsRunning(false);
    setCurrentPrompt('');
    setMode(null);
  }, []);

  return {
    events,
    isRunning,
    startScenario,
    abort,
  };
}
