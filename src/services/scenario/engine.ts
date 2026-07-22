import type { Scenario, ScenarioEvent } from '../../types/scenario';
import { getEventDelay } from './delays';
import type { ScenarioListener, ScenarioRunner } from './types';

export const runScenario = (scenario: Scenario, onEvent: ScenarioListener, onComplete: () => void): ScenarioRunner => {
  let aborted = false;
  const timeoutIds: ReturnType<typeof setTimeout>[] = [];

  const abort = () => {
    aborted = true;
    timeoutIds.forEach(clearTimeout);
    timeoutIds.length = 0;
  };

  const scheduleEvents = (events: ScenarioEvent[], startIndex: number) => {
    let cumulativeDelay = 0;

    for (let i = startIndex; i < events.length; i++) {
      if (aborted) break;

      const event = events[i];
      const currentDelay = cumulativeDelay;

      const timeoutId = setTimeout(() => {
        if (aborted) return;
        onEvent(event, i);

        if (i === events.length - 1) {
          const finalDelay = setTimeout(() => {
            if (!aborted) onComplete();
          }, 500);
          timeoutIds.push(finalDelay);
        }
      }, currentDelay);

      timeoutIds.push(timeoutId);

      // Add event delay for the NEXT event in the sequence
      cumulativeDelay += getEventDelay(event);
    }
  };

  scheduleEvents(scenario.events, 0);

  return { abort };
};
