import { Scenario, ScenarioEvent, ScenarioMode } from '../../types/scenario';
import { buildScenario } from './scenarios/buildScenario';
import { planScenario } from './scenarios/planScenario';
import { reactDashboardScenario } from './scenarios/reactDashboardScenario';
import { dockerScenario } from './scenarios/dockerScenario';
import { cicdScenario } from './scenarios/cicdScenario';
import { apiPlanScenario } from './scenarios/apiPlanScenario';
import { reactPlanScenario } from './scenarios/reactPlanScenario';
import { dockerPlanScenario } from './scenarios/dockerPlanScenario';
import { cicdPlanScenario } from './scenarios/cicdPlanScenario';

export type ScenarioListener = (event: ScenarioEvent, index: number) => void;

export interface ScenarioRunner {
  abort: () => void;
}

export const runScenario = (
  scenario: Scenario,
  onEvent: ScenarioListener,
  onComplete: () => void,
  onThinkingToggle?: (visible: boolean) => void
): ScenarioRunner => {
  let aborted = false;
  let timeoutIds: ReturnType<typeof setTimeout>[] = [];

  const abort = () => {
    aborted = true;
    timeoutIds.forEach(clearTimeout);
    timeoutIds = [];
  };

  const scheduleEvents = (events: ScenarioEvent[], startIndex: number) => {
    let cumulativeDelay = 0;

    for (let i = startIndex; i < events.length; i++) {
      if (aborted) break;

      const event = events[i];
      const eventDelay = getEventDelay(event);
      cumulativeDelay += eventDelay;

      const timeoutId = setTimeout(() => {
        if (aborted) return;
        onEvent(event, i);

        if (i === events.length - 1) {
          const finalDelay = setTimeout(() => {
            if (!aborted) onComplete();
          }, 500);
          timeoutIds.push(finalDelay);
        }
      }, cumulativeDelay);

      timeoutIds.push(timeoutId);
    }
  };

  scheduleEvents(scenario.events, 0);

  return { abort };
};

const getEventDelay = (event: ScenarioEvent): number => {
  switch (event.kind) {
    case 'thinking':
      return event.duration;
    case 'file_create':
      return 800;
    case 'file_edit':
      return 600;
    case 'file_delete':
      return 400;
    case 'terminal':
      return event.duration + 400;
    case 'error':
      return 600;
    case 'warning':
      return 400;
    case 'retry':
      return 400;
    case 'success':
      return 300;
    case 'summary':
      return 200;
    case 'message':
      return 300;
    case 'progress':
      return 400;
    case 'waiting':
      return event.duration;
    case 'test_execution':
      return 1000;
    case 'build_step':
      return (event.duration ?? 500) + 300;
    case 'deployment':
      return 800;
    case 'analysis':
      return event.sections.length * 200 + 300;
    default:
      return 300;
  }
};

interface ScenarioMatcher {
  keywords: string[];
  build: (prompt: string) => Scenario;
  plan: (prompt: string) => Scenario;
}

const matchers: ScenarioMatcher[] = [
  {
    keywords: ['react', 'dashboard', 'frontend', 'ui', 'component', 'recharts', 'chart', 'next.js', 'vite', 'web app'],
    build: reactDashboardScenario,
    plan: reactPlanScenario,
  },
  {
    keywords: ['docker', 'container', 'compose', 'dockerfile', 'nginx', 'containerize', 'k8s'],
    build: dockerScenario,
    plan: dockerPlanScenario,
  },
  {
    keywords: ['ci/cd', 'ci cd', 'pipeline', 'github actions', 'workflow', 'deploy', 'automation', 'actions'],
    build: cicdScenario,
    plan: cicdPlanScenario,
  },
  {
    keywords: ['api', 'rest', 'crud', 'backend', 'fastapi', 'endpoint', 'route', 'database', 'user'],
    build: buildScenario,
    plan: apiPlanScenario,
  },
];

const matchScenario = (prompt: string, mode: ScenarioMode): Scenario => {
  const lower = prompt.toLowerCase();

  // Detect inline mode overrides in prompt string
  let effectiveMode: ScenarioMode = mode;
  if (lower.includes('[plan]') || lower.includes('--plan') || lower.includes('/plan')) {
    effectiveMode = 'plan';
  } else if (lower.includes('[build]') || lower.includes('--build') || lower.includes('/build')) {
    effectiveMode = 'build';
  }

  // Match prompt keywords to topic category
  for (const matcher of matchers) {
    if (matcher.keywords.some(kw => lower.includes(kw))) {
      return matcher[effectiveMode](prompt);
    }
  }

  // Fallback: generic scenario per effective mode
  if (effectiveMode === 'plan') {
    return planScenario(prompt);
  }
  return buildScenario(prompt);
};

export const getScenarioForPrompt = (prompt: string, mode: ScenarioMode): Scenario => {
  return matchScenario(prompt, mode);
};
