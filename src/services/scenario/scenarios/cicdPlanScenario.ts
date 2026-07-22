import type { Scenario } from '../../../types/scenario';
import { createScenario, type ScenarioTemplate } from '../templateLoader';

const template: ScenarioTemplate = {
  mode: 'plan',
  events: [
    {
      kind: 'thinking',
      thoughts: [
        {
          text: 'Analyzing CI/CD prompt intent: evaluating GitHub Actions workflow, matrix runner strategy, and Helm release',
          delay: 250,
        },
        {
          text: 'Inspecting repository triggers: pull requests to main, release tag pushes, and manual workflow dispatches',
          delay: 300,
        },
        {
          text: 'Architecting 3-stage CI/CD pipeline: Static Analysis -> Parallel Test Matrix -> Container Build & Deploy',
          delay: 350,
        },
        {
          text: 'Formulating OIDC security scope, least privilege token permissions, npm dependency caching, and act local runner',
          delay: 300,
        },
        {
          text: 'Designing Kubernetes Helm chart deployment rollback safety and slack notification webhooks',
          delay: 250,
        },
      ],
      duration: 1600,
    },
    {
      kind: 'terminal',
      command: 'git remote -v',
      output: [
        'origin  git@github.com:zenith-org/zenith-app.git (fetch)',
        'origin  git@github.com:zenith-org/zenith-app.git (push)',
      ],
      duration: 400,
    },
    {
      kind: 'analysis',
      title: 'GitHub Actions CI/CD Pipeline Architecture',
      sections: [
        {
          title: '1. Workflow Pipeline Trigger & Job Matrix',
          items: [
            'Trigger Scope: Pushes to `main` branch, pull requests targeting `main`, and tag pushes `v*.*.*`',
            'Job 1 (Quality Gate): `lint-and-typecheck` (Biome check + TypeScript strict compiler execution)',
            'Job 2 (Parallel Test Matrix): `test-matrix` executing Vitest across Node.js 18, 20, and 22 runtimes',
            'Job 3 (Release & Deploy): `build-and-push` constructing multi-stage Docker container & publishing to GHCR',
          ],
        },
        {
          title: '2. Security Scope & Token Permissions (OIDC)',
          items: [
            'Token Scope: `permissions: { contents: read, id-token: write, security-events: write }`',
            'Authentication: OpenID Connect (OIDC) passwordless cloud provider authentication (zero long-lived secrets)',
            'Dependency Caching: `actions/setup-node` with `cache: npm` for deterministic speedups',
          ],
        },
        {
          title: '3. Target Configuration Files',
          items: [
            '.github/workflows/ci.yml (Primary CI/CD pipeline definition)',
            '.github/workflows/release.yml (Tag release & Helm chart deployment)',
            '.github/dependabot.yml (Automated weekly dependency security updates)',
          ],
        },
        {
          title: '4. Local Simulation & Verification Strategy',
          items: [
            'Local Execution: `act -j lint-and-typecheck` to run GitHub Actions locally prior to pushing',
            'Coverage Enforcement: Codecov step failing PR if overall test coverage drops below 90%',
          ],
        },
      ],
    },
    {
      kind: 'summary',
      title: 'CI/CD Pipeline Architecture Plan Ready',
      description:
        'The GitHub Actions workflow pipeline design, OIDC security token scope, parallel matrix runner strategy, and target file tree have been generated.',
      filesCreated: [],
      commandsExecuted: ['git remote -v'],
      verified: [
        'GitHub Actions 3-Stage Pipeline Design',
        'Parallel Node 18/20/22 Test Matrix',
        'OIDC Least-Privilege Security Scope',
        'Act Local Runner Verification Strategy',
      ],
    },
    {
      kind: 'planner_action_panel',
      defaultFilename: 'zenith_plans/implementation-plan.md',
      saved: false,
    },
  ],
};

export const cicdPlanScenario = (prompt: string): Scenario => createScenario(prompt, template);
