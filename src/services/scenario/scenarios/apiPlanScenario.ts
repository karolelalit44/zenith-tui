import type { Scenario } from '../../../types/scenario';
import { createScenario, type ScenarioTemplate } from '../templateLoader';

const template: ScenarioTemplate = {
  mode: 'plan',
  events: [
    {
      kind: 'thinking',
      thoughts: [
        {
          text: 'Analyzing backend API prompt intent: evaluating REST / gRPC endpoint requirements and database tier',
          delay: 250,
        },
        {
          text: 'Inspecting backend workspace configuration: checking Python / Node.js runtime and ORM schemas',
          delay: 300,
        },
        {
          text: 'Architecting RESTful resource routes (v1 API), Pydantic v2 domain models, and JWT authentication flow',
          delay: 350,
        },
        {
          text: 'Designing PostgreSQL database migrations (Alembic), Redis query caching layer, and OpenAPI 3.1 spec generation',
          delay: 300,
        },
        {
          text: 'Formulating end-to-end execution roadmap, test suite plan (Pytest asyncio), and risk matrix',
          delay: 250,
        },
      ],
      duration: 1600,
    },
    {
      kind: 'terminal',
      command: 'git status --porcelain',
      output: ['On branch main', 'nothing to commit, working tree clean'],
      duration: 400,
    },
    {
      kind: 'terminal',
      command: 'find backend/ -maxdepth 3 -not -path "*/.*"',
      output: ['backend/', 'backend/app/', 'backend/app/main.py', 'backend/requirements.txt'],
      duration: 500,
    },
    {
      kind: 'analysis',
      title: 'Enterprise REST API Architecture & Data Tier Strategy',
      sections: [
        {
          title: '1. API Endpoint Specification (v1 OpenAPI 3.1)',
          items: [
            'POST /api/v1/auth/login -> Authenticate user credentials & issue JWT access + refresh tokens',
            'POST /api/v1/users -> Register user account with Pydantic v2 payload validation & password hashing',
            'GET  /api/v1/users/me -> Retrieve authenticated user profile with JWT Bearer Token dependency',
            'GET  /api/v1/analytics/realtime -> SSE (Server-Sent Events) streaming analytics endpoint',
          ],
        },
        {
          title: '2. Database & Caching Tier',
          items: [
            'Relational Storage: PostgreSQL 16 with SQLAlchemy 2.0 async session pool (min_size=5, max_size=20)',
            'Migration Control: Alembic version tracking for zero-downtime schema evolution',
            'Caching Tier: Redis 7.2 cluster for JWT blacklist revocation and rate-limiting counters (100 req/min)',
          ],
        },
        {
          title: '3. Estimated Target File Tree',
          items: [
            'backend/app/schemas/user.py (Pydantic v2 domain schemas)',
            'backend/app/models/user.py (SQLAlchemy 2.0 ORM entity definitions)',
            'backend/app/services/auth_service.py (Bcrypt hashing & JWT token operations)',
            'backend/app/api/v1/endpoints/users.py (FastAPI router handlers)',
            'backend/tests/test_api_v1.py (Pytest asyncio HTTP integration tests)',
          ],
        },
        {
          title: '4. Security & Performance Guardrails',
          items: [
            'Authentication: OAuth2 Password Bearer flow with HS256 JWT signature verification',
            'Rate Limiting: SlowAPI sliding window algorithm protecting POST endpoints against brute-force attacks',
            'Static Type Compliance: Mypy strict mode validation enforced in CI pipeline',
          ],
        },
      ],
    },
    {
      kind: 'summary',
      title: 'REST API Architecture Plan Ready',
      description:
        'The API endpoint specification, database tier strategy, authentication security guardrails, and file tree breakdown have been generated.',
      filesCreated: [],
      commandsExecuted: ['git status', 'find backend/'],
      verified: [
        'OpenAPI 3.1 Endpoint Specifications',
        'PostgreSQL SQLAlchemy 2.0 & Redis Caching Strategy',
        'OAuth2 JWT Security Guardrails',
        'Estimated File Breakdown & Pytest Testing Plan',
      ],
    },
    {
      kind: 'planner_action_panel',
      defaultFilename: 'zenith_plans/implementation-plan.md',
      saved: false,
    },
  ],
};

export const apiPlanScenario = (prompt: string): Scenario => createScenario(prompt, template);
