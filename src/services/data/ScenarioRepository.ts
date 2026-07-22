import { Scenario, ScenarioMode } from '../../types/scenario';
import { apiPlanScenario } from '../scenario/scenarios/apiPlanScenario';
import { buildScenario } from '../scenario/scenarios/build/buildScenario';
import { cicdPlanScenario } from '../scenario/scenarios/cicdPlanScenario';
import { cicdScenario } from '../scenario/scenarios/cicdScenario';
import { dockerPlanScenario } from '../scenario/scenarios/dockerPlanScenario';
import { dockerScenario } from '../scenario/scenarios/dockerScenario';
import { modeMismatchScenario, providerErrorScenario, systemErrorScenario } from '../scenario/scenarios/errorScenarios';
import { planScenario } from '../scenario/scenarios/plan/planScenario';
import { reactDashboardScenario } from '../scenario/scenarios/reactDashboardScenario';
import { reactPlanScenario } from '../scenario/scenarios/reactPlanScenario';

interface ScenarioMatcher {
  keywords: string[];
  build: (prompt: string) => Scenario;
  plan: (prompt: string) => Scenario;
}

const scenarioMatchers: ScenarioMatcher[] = [
  {
    keywords: ['react', 'dashboard', 'frontend', 'ui', 'component', 'view', 'vite', 'tailwind'],
    build: reactDashboardScenario,
    plan: reactPlanScenario,
  },
  {
    keywords: ['docker', 'container', 'dockerfile', 'compose', 'image', 'nginx', 'alpine'],
    build: dockerScenario,
    plan: dockerPlanScenario,
  },
  {
    keywords: ['ci', 'cd', 'pipeline', 'github actions', 'workflow', 'deploy', 'kubernetes', 'act'],
    build: cicdScenario,
    plan: cicdPlanScenario,
  },
  {
    keywords: ['api', 'rest', 'crud', 'backend', 'fastapi', 'endpoint', 'route', 'database', 'user'],
    build: buildScenario,
    plan: apiPlanScenario,
  },
];

export const getScenarioForPrompt = (prompt: string, mode: ScenarioMode): Scenario => {
  const lower = prompt.toLowerCase();

  // Test Error Triggers
  if (lower.includes('rate limit') || lower.includes('api key') || lower.includes('provider error')) {
    return providerErrorScenario(prompt);
  }
  if (lower.includes('permission denied') || lower.includes('system error')) {
    return systemErrorScenario(prompt);
  }

  // Explicit Mode Mismatch Triggers
  if (
    mode === 'plan' &&
    (lower.includes('generate code') || lower.includes('create file') || lower.includes('write implementation'))
  ) {
    return modeMismatchScenario(prompt, 'plan');
  }

  // Inline mode overrides
  let effectiveMode: ScenarioMode = mode;
  if (lower.includes('[plan]') || lower.includes('--plan') || lower.includes('/plan')) {
    effectiveMode = 'plan';
  } else if (lower.includes('[build]') || lower.includes('--build') || lower.includes('/build')) {
    effectiveMode = 'build';
  }

  // Keyword Matchers
  for (const matcher of scenarioMatchers) {
    if (matcher.keywords.some((kw) => lower.includes(kw))) {
      return matcher[effectiveMode](prompt);
    }
  }

  // Fallbacks
  if (effectiveMode === 'plan') {
    return planScenario(prompt);
  }
  return buildScenario(prompt);
};
