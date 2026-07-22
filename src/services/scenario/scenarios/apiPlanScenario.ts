import { Scenario } from '../../../types/scenario';

let idCounter = 0;
const uid = () => `plan_api_${++idCounter}`;

export const apiPlanScenario = (prompt: string): Scenario => ({
  id: `plan_api_${Date.now()}`,
  mode: 'plan',
  prompt,
  events: [
    {
      kind: 'thinking',
      id: uid(),
      thoughts: [
        { text: 'Analyzing API requirements', delay: 300 },
        { text: 'Identifying endpoints and data models', delay: 400 },
        { text: 'Evaluating framework options', delay: 350 },
        { text: 'Assessing authentication needs', delay: 300 },
      ],
      duration: 1500,
    },
    {
      kind: 'analysis',
      id: uid(),
      title: 'API Architecture',
      sections: [
        {
          title: 'Endpoints',
          items: [
            'GET /api/resources — List all resources',
            'GET /api/resources/:id — Get single resource',
            'POST /api/resources — Create new resource',
            'PUT /api/resources/:id — Update resource',
            'DELETE /api/resources/:id — Delete resource',
          ],
        },
        {
          title: 'Data Models',
          items: [
            'Resource model with id, name, created_at, updated_at',
            'User model with id, email, role, permissions',
            'Relationship: User has many Resources',
          ],
        },
      ],
    },
    {
      kind: 'thinking',
      id: uid(),
      thoughts: [
        { text: 'Planning database schema', delay: 350 },
        { text: 'Designing error handling strategy', delay: 300 },
        { text: 'Evaluating rate limiting approach', delay: 400 },
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
            '8-12 source files',
            '3-4 configuration files',
            '2-3 test files',
            '1 migration file',
          ],
        },
        {
          title: 'Dependencies',
          items: [
            'Framework: FastAPI or Express',
            'Database: PostgreSQL with SQLAlchemy/Prisma',
            'Auth: JWT with refresh tokens',
            'Testing: Pytest or Vitest',
          ],
        },
        {
          title: 'Risks',
          items: [
            'Database migration complexity',
            'Authentication token expiry handling',
            'Input validation edge cases',
          ],
        },
      ],
    },
    {
      kind: 'message',
      id: uid(),
      text: 'API architecture analysis complete. Switch to Build mode to implement.',
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
