import { Scenario } from '../../../types/scenario';

let idCounter = 0;
const uid = () => `plan_docker_${++idCounter}`;

export const dockerPlanScenario = (prompt: string): Scenario => ({
  id: `plan_docker_${Date.now()}`,
  mode: 'plan',
  prompt,
  events: [
    {
      kind: 'thinking',
      id: uid(),
      thoughts: [
        { text: 'Analyzing application for containerization', delay: 300 },
        { text: 'Identifying runtime dependencies', delay: 400 },
        { text: 'Evaluating multi-stage build needs', delay: 350 },
        { text: 'Assessing networking requirements', delay: 300 },
      ],
      duration: 1500,
    },
    {
      kind: 'analysis',
      id: uid(),
      title: 'Container Architecture',
      sections: [
        {
          title: 'Services',
          items: [
            'App service (Node.js / Python / Go)',
            'Database service (PostgreSQL / MongoDB)',
            'Cache service (Redis)',
            'Reverse proxy (Nginx / Traefik)',
          ],
        },
        {
          title: 'Networking',
          items: [
            'Internal bridge network for service communication',
            'Exposed ports for external access',
            'Health check endpoints per service',
          ],
        },
      ],
    },
    {
      kind: 'thinking',
      id: uid(),
      thoughts: [
        { text: 'Planning volume mounts for persistence', delay: 350 },
        { text: 'Designing environment variable strategy', delay: 300 },
        { text: 'Evaluating security constraints', delay: 400 },
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
            '1-2 Dockerfiles (multi-stage)',
            '1 docker-compose.yml',
            '1 .dockerignore',
            '1 nginx.conf (if applicable)',
          ],
        },
        {
          title: 'Dependencies',
          items: [
            'Base images: node:20-alpine, python:3.12-slim',
            'Build tools: npm, pip, cargo',
            'Runtime: nginx:alpine for static serving',
          ],
        },
        {
          title: 'Risks',
          items: [
            'Image size optimization',
            'Secret management in containers',
            'Data persistence across rebuilds',
          ],
        },
      ],
    },
    {
      kind: 'message',
      id: uid(),
      text: 'Container architecture analysis complete. Switch to Build mode to implement.',
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
