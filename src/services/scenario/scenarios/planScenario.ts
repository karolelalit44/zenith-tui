import { Scenario } from '../../../types/scenario';

let idCounter = 0;
const uid = () => `plan_${++idCounter}`;

export const planScenario = (prompt: string): Scenario => ({
  id: `plan_${Date.now()}`,
  mode: 'plan',
  prompt,
  events: [
    {
      kind: 'thinking',
      id: uid(),
      thoughts: [
        { text: 'Analyzing the request', delay: 300 },
        { text: 'Identifying core requirements', delay: 400 },
        { text: 'Evaluating technology options', delay: 350 },
        { text: 'Assessing complexity and scope', delay: 300 },
      ],
      duration: 1500,
    },
    {
      kind: 'analysis',
      id: uid(),
      title: 'Task Breakdown',
      sections: [
        {
          title: 'Architecture',
          items: [
            'Component-based frontend with state management',
            'RESTful API layer with proper error handling',
            'Database schema with migration support',
            'Authentication and authorization middleware',
          ],
        },
        {
          title: 'Implementation Plan',
          items: [
            'Phase 1: Project scaffolding and dependencies',
            'Phase 2: Core data models and database setup',
            'Phase 3: API endpoints and business logic',
            'Phase 4: Frontend components and routing',
            'Phase 5: Integration testing and validation',
          ],
        },
      ],
    },
    {
      kind: 'thinking',
      id: uid(),
      thoughts: [
        { text: 'Mapping dependencies between components', delay: 350 },
        { text: 'Identifying critical path', delay: 300 },
        { text: 'Evaluating risks and mitigation strategies', delay: 400 },
      ],
      duration: 1200,
    },
    {
      kind: 'analysis',
      id: uid(),
      title: 'Dependencies and Risks',
      sections: [
        {
          title: 'Estimated Files',
          items: [
            '12-15 source files',
            '4-6 configuration files',
            '3-5 test files',
            '1-2 documentation files',
          ],
        },
        {
          title: 'Key Dependencies',
          items: [
            'Framework: React 19 or Next.js 15',
            'Styling: Tailwind CSS v4',
            'State: Zustand or React Context',
            'Testing: Vitest + Testing Library',
          ],
        },
        {
          title: 'Risks',
          items: [
            'Database migration compatibility with production',
            'Third-party API rate limits during testing',
            'Performance implications of real-time updates',
          ],
        },
      ],
    },
    {
      kind: 'message',
      id: uid(),
      text: 'Analysis complete. Switch to Build mode to execute this plan.',
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
