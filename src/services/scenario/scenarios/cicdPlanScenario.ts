import { Scenario } from '../../../types/scenario';

let idCounter = 0;
const uid = () => `plan_ci_${Date.now()}_${++idCounter}`;

export const cicdPlanScenario = (prompt: string): Scenario => ({
  id: `plan_ci_${Date.now()}`,
  mode: 'plan',
  prompt,
  events: [
    {
      kind: 'thinking',
      id: uid(),
      thoughts: [
        { text: `Analyzing CI/CD Pipeline prompt: "${prompt}"`, delay: 250 },
        { text: 'Evaluating GitHub Actions matrix builds & npm cache optimization', delay: 300 },
        { text: 'Designing multi-environment pipeline triggers (Staging vs Production)', delay: 300 },
      ],
      duration: 1200,
    },
    {
      kind: 'terminal',
      id: uid(),
      command: 'git remote -v',
      output: [
        'origin  git@github.com:acme/zenith-app.git (fetch)',
        'origin  git@github.com:acme/zenith-app.git (push)',
      ],
      duration: 400,
    },
    {
      kind: 'terminal',
      id: uid(),
      command: 'cat .github/workflows/ci.yml',
      output: [
        'cat: .github/workflows/ci.yml: No such file or directory',
      ],
      duration: 450,
    },
    {
      kind: 'thinking',
      id: uid(),
      thoughts: [
        { text: 'No existing GitHub Actions workflows detected', delay: 300 },
        { text: 'Designing full multi-job workflow architecture (Lint -> Test -> Build -> Deploy)', delay: 300 },
      ],
      duration: 1000,
    },
    {
      kind: 'retry',
      id: uid(),
      message: 'Generating complete GitHub Actions workflow specification',
      attempt: 1,
    },
    {
      kind: 'analysis',
      id: uid(),
      title: 'CI/CD Pipeline Architecture & Stages',
      sections: [
        {
          title: 'Pipeline Job Graph',
          items: [
            'Job 1: Static Analysis (ESLint + TypeScript type check)',
            'Job 2: Automated Testing (Vitest unit tests with coverage upload)',
            'Job 3: Production Build (Vite bundling & Docker image compilation)',
            'Job 4: Staging & Production Deployment (Kubernetes / Cloud release)',
          ],
        },
        {
          title: 'Workflow Triggers',
          items: [
            'Push to main: Full test, build, and staging deployment pipeline',
            'Pull Requests: Fast lint, type-check, and unit test validation',
            'Release Tag (v*): Automated production deployment & registry push',
          ],
        },
      ],
    },
    {
      kind: 'analysis',
      id: uid(),
      title: 'Target Files, Secrets & Security Strategy',
      sections: [
        {
          title: 'Target Workflow Files',
          items: [
            '.github/workflows/ci.yml (Main test and build pipeline)',
            '.github/workflows/cd.yml (Staging & production deployment workflow)',
          ],
        },
        {
          title: 'Secrets & Risk Matrix',
          items: [
            'Required Repository Secrets: REGISTRY_TOKEN, KUBE_CONFIG, SLACK_WEBHOOK',
            'Risk: Secret leakage in build logs -> Mitigation: Mask secrets and use OIDC tokens',
          ],
        },
      ],
    },
    {
      kind: 'summary',
      id: uid(),
      title: 'CI/CD Architecture Plan Ready',
      description: 'The GitHub Actions workflow specification and multi-stage deployment plan have been generated.',
      filesCreated: [],
      commandsExecuted: [
        'git remote -v',
        'cat .github/workflows/ci.yml (initial check)',
      ],
      verified: [
        'GitHub Actions v4 specification',
        'Multi-stage job dependency graph',
        'Secret security & OIDC auth',
        'Environment deployment rules',
      ],
    },
    {
      kind: 'planner_action_panel',
      id: uid(),
      defaultFilename: 'implementation-plan.md',
    },
  ],
});
