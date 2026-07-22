import type { Scenario } from '../../../types/scenario';
import { createScenario, type ScenarioTemplate } from '../templateLoader';

const buildTemplate = (prompt: string): ScenarioTemplate => ({
  mode: 'plan',
  events: [
    {
      kind: 'thinking',
      thoughts: [
        { text: `Analyzing API & Backend prompt: "${prompt}"`, delay: 250 },
        { text: 'Evaluating FastAPI REST endpoints & Pydantic v2 domain schemas', delay: 300 },
        { text: 'Planning PostgreSQL database migration strategy & auth middleware', delay: 300 },
      ],
      duration: 1200,
    },
    {
      kind: 'terminal',
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
      command: 'python -c "import fastapi, pydantic; print(fastapi.__version__, pydantic.__version__)"',
      output: ['0.109.0 2.6.0'],
      duration: 500,
    },
    {
      kind: 'thinking',
      thoughts: [
        { text: 'FastAPI 0.109 and Pydantic 2.6 verified in local environment', delay: 300 },
        { text: 'Designing RESTful endpoint routing structure & database schemas', delay: 300 },
      ],
      duration: 1000,
    },
    {
      kind: 'analysis',
      title: 'REST API Architecture & Endpoint Specification',
      sections: [
        {
          title: 'Endpoints Specification',
          items: [
            'GET /api/users — List paginated users (query params: skip, limit, search)',
            'GET /api/users/{id} — Retrieve user profile by ID',
            'POST /api/users — Register new user with Pydantic schema validation',
            'PUT /api/users/{id} — Update user profile details',
            'DELETE /api/users/{id} — Soft-delete user account',
          ],
        },
        {
          title: 'Data & Schema Layer',
          items: [
            'Domain Models: UserBase, UserCreate, UserResponse, UserUpdate',
            'Database ORM: SQLAlchemy async engine with Alembic migrations',
            'Authentication: OAuth2 Bearer password flow with JWT tokens',
          ],
        },
      ],
    },
    {
      kind: 'analysis',
      title: 'Target Files, Risk Assessment & Optimization',
      sections: [
        {
          title: 'Estimated File Tree',
          items: [
            'backend/app/main.py (FastAPI app entrypoint & middleware)',
            'backend/app/models.py (Pydantic domain schemas)',
            'backend/app/api/users.py (User CRUD route handlers)',
            'backend/app/api/__init__.py (Router exports)',
          ],
        },
        {
          title: 'Risks & Mitigation Strategies',
          items: [
            'Risk: Database connection pool starvation -> Mitigation: SQLAlchemy AsyncSession with pool size 20',
            'Risk: Unhandled Pydantic validation errors -> Mitigation: Global RequestValidationError handler',
          ],
        },
      ],
    },
    {
      kind: 'summary',
      title: 'REST API Architecture Plan Ready',
      description:
        'The FastAPI endpoint design, Pydantic schemas, and SQLAlchemy data architecture plan have been generated.',
      filesCreated: [],
      commandsExecuted: ['git status', 'python -c "import fastapi, pydantic"'],
      verified: [
        'FastAPI 0.109 & Pydantic 2.6 environment',
        'RESTful endpoint specification',
        'OAuth2 & JWT authentication model',
        'File structure breakdown',
      ],
    },
    {
      kind: 'planner_action_panel',
      defaultFilename: 'implementation-plan.md',
    },
  ],
});

export const apiPlanScenario = (prompt: string): Scenario => createScenario(prompt, buildTemplate(prompt));
