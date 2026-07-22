import { Scenario } from '../../../types/scenario';

let idCounter = 0;
const uid = () => `plan_${Date.now()}_${++idCounter}`;

export const planScenario = (prompt: string): Scenario => ({
  id: `plan_${Date.now()}`,
  mode: 'plan',
  prompt,
  events: [
    // Phase 1: Reasoning & Requirements Analysis
    {
      kind: 'thinking',
      id: uid(),
      thoughts: [
        { text: `Analyzing request: "${prompt}"`, delay: 250 },
        { text: 'Deconstructing core system components & goals', delay: 300 },
        { text: 'Identifying technical milestones & architectural layers', delay: 300 },
      ],
      duration: 1200,
    },

    // Phase 2: Terminal Inspection & Discovery
    {
      kind: 'terminal',
      id: uid(),
      command: 'git status',
      output: [
        'On branch main',
        'Your branch is up to date with "origin/main".',
        'nothing to commit, working tree clean',
      ],
      duration: 400,
    },
    {
      kind: 'terminal',
      id: uid(),
      command: 'npx check-workspace',
      output: [
        'Error: Could not locate workspace configuration manifest.',
        'MISSING_MANIFEST: ./workspace.config.json',
      ],
      duration: 500,
    },

    // Phase 3: Failure Analysis & Automated Recovery
    {
      kind: 'thinking',
      id: uid(),
      thoughts: [
        { text: 'Detected missing workspace configuration manifest', delay: 300 },
        { text: 'Switching to fallback inspection: parsing package.json dependencies', delay: 300 },
      ],
      duration: 1000,
    },
    {
      kind: 'retry',
      id: uid(),
      message: 'Retrying workspace discovery using fallback package inspection',
      attempt: 2,
    },
    {
      kind: 'terminal',
      id: uid(),
      command: 'cat package.json | grep -E "dependencies|devDependencies"',
      output: [
        '  "dependencies": { "fastapi": "^0.109.0", "pydantic": "^2.6.0" },',
        '  "devDependencies": { "vitest": "^1.2.0", "typescript": "^5.3.0" }',
      ],
      duration: 450,
    },

    // Phase 4: Architectural Roadmap & Task Breakdown
    {
      kind: 'analysis',
      id: uid(),
      title: 'Architectural Roadmap & System Design',
      sections: [
        {
          title: 'System Architecture',
          items: [
            'API Layer: Modular REST endpoints with Pydantic schema validation',
            'Data Layer: Async ORM models with migration tracking',
            'Service Layer: Decoupled business logic & repository pattern',
            'Security Layer: JWT authentication & rate limiting middleware',
          ],
        },
        {
          title: 'Implementation Milestones',
          items: [
            'Milestone 1: Project scaffolding & environment configuration',
            'Milestone 2: Database schemas & data access layer',
            'Milestone 3: REST API route handlers & validation schemas',
            'Milestone 4: Automated test suite & CI validation',
          ],
        },
      ],
    },
    {
      kind: 'thinking',
      id: uid(),
      thoughts: [
        { text: 'Evaluating dependencies & potential production risks', delay: 300 },
        { text: 'Finalizing execution roadmap and file tree structure', delay: 300 },
      ],
      duration: 1000,
    },
    {
      kind: 'analysis',
      id: uid(),
      title: 'Dependencies, Risk Assessment & File Tree',
      sections: [
        {
          title: 'Target File Structure',
          items: [
            'backend/app/main.py (App entrypoint & router initialization)',
            'backend/app/models.py (Data schemas & Pydantic domain models)',
            'backend/app/api/users.py (User CRUD API handlers)',
            'backend/requirements.txt (Dependencies manifest)',
          ],
        },
        {
          title: 'Risks & Mitigation Strategies',
          items: [
            'Risk: Database migration lockup under concurrent traffic -> Mitigation: Connection pooling',
            'Risk: Unhandled schema validation errors -> Mitigation: Centralized exception handlers',
          ],
        },
      ],
    },

    // Phase 5: Plan Completion Summary & Save Action Panel
    {
      kind: 'summary',
      id: uid(),
      title: 'Implementation Plan Ready',
      description: 'The architectural plan and step-by-step roadmap have been generated.',
      filesCreated: [],
      commandsExecuted: [
        'git status',
        'npx check-workspace (fallback recovered)',
        'cat package.json',
      ],
      verified: [
        'System Architecture',
        'Milestone Breakdown',
        'Risk Mitigation Strategy',
        'Target File Structure',
      ],
    },
    {
      kind: 'planner_action_panel',
      id: uid(),
      defaultFilename: 'zenith_plans/implementation-plan.md',
    },
  ],
});
