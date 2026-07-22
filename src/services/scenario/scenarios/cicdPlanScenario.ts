import { Scenario } from '../../../types/scenario';

let idCounter = 0;
const uid = () => `plan_ci_${++idCounter}`;

export const cicdPlanScenario = (prompt: string): Scenario => ({
  id: `plan_ci_${Date.now()}`,
  mode: 'plan',
  prompt,
  events: [
    {
      kind: 'thinking',
      id: uid(),
      thoughts: [
        { text: 'Analyzing repository structure', delay: 300 },
        { text: 'Identifying build and test commands', delay: 400 },
        { text: 'Evaluating deployment targets', delay: 350 },
        { text: 'Assessing environment requirements', delay: 300 },
      ],
      duration: 1500,
    },
    {
      kind: 'analysis',
      id: uid(),
      title: 'Pipeline Architecture',
      sections: [
        {
          title: 'Stages',
          items: [
            'Lint & Type Check — Static analysis',
            'Unit Tests — Component and unit tests',
            'Build — Compile and bundle',
            'Integration Tests — E2E and API tests',
            'Deploy — Push to staging/production',
          ],
        },
        {
          title: 'Triggers',
          items: [
            'Push to main → Full pipeline',
            'Pull request → Lint + Test + Build',
            'Tag release → Deploy to production',
          ],
        },
      ],
    },
    {
      kind: 'thinking',
      id: uid(),
      thoughts: [
        { text: 'Planning caching strategy', delay: 350 },
        { text: 'Designing secret management', delay: 300 },
        { text: 'Evaluating parallelization opportunities', delay: 400 },
      ],
      duration: 1200,
    },
    {
      kind: 'analysis',
      id: uid(),
      title: 'Implementation Plan',
      sections: [
        {
          title: 'Estimated Files',
          items: [
            '1-2 workflow YAML files',
            '1 Dockerfile (for containerized deploys)',
            '1 deployment config (K8s / Cloud)',
          ],
        },
        {
          title: 'Dependencies',
          items: [
            'CI Platform: GitHub Actions / GitLab CI',
            'Registry: Docker Hub / GHCR',
            'Deploy: Vercel / AWS / Kubernetes',
          ],
        },
        {
          title: 'Risks',
          items: [
            'Secret exposure in logs',
            'Flaky test causing pipeline failures',
            'Deployment rollback complexity',
          ],
        },
      ],
    },
    {
      kind: 'message',
      id: uid(),
      text: 'CI/CD architecture analysis complete. Switch to Build mode to implement.',
    },
    {
      kind: 'success',
      id: uid(),
      message: 'Plan generated successfully',
      filesCreated: [],
      commandsExecuted: [],
    },
  ],
});
