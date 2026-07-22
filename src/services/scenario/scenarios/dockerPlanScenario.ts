import { Scenario } from '../../../types/scenario';

let idCounter = 0;
const uid = () => `plan_docker_${Date.now()}_${++idCounter}`;

export const dockerPlanScenario = (prompt: string): Scenario => ({
  id: `plan_docker_${Date.now()}`,
  mode: 'plan',
  prompt,
  events: [
    {
      kind: 'thinking',
      id: uid(),
      thoughts: [
        { text: `Analyzing Docker container prompt: "${prompt}"`, delay: 250 },
        { text: 'Evaluating multi-stage build optimization & Alpine Linux security', delay: 300 },
        { text: 'Planning Docker Compose service topology, volumes & bridge networks', delay: 300 },
      ],
      duration: 1200,
    },
    {
      kind: 'terminal',
      id: uid(),
      command: 'docker info',
      output: [
        'Client: Docker Engine - Community',
        ' Server Version: 26.0.0',
        ' Storage Driver: overlay2',
        ' Cgroup Driver: systemd',
      ],
      duration: 400,
    },
    {
      kind: 'terminal',
      id: uid(),
      command: 'docker compose config --quiet',
      output: [
        'Error: docker-compose.yml file not found in working directory.',
      ],
      duration: 450,
    },
    {
      kind: 'thinking',
      id: uid(),
      thoughts: [
        { text: 'Detected missing docker-compose.yml manifest', delay: 300 },
        { text: 'Designing multi-service compose schema from project dependencies', delay: 300 },
      ],
      duration: 1000,
    },
    {
      kind: 'retry',
      id: uid(),
      message: 'Generating new multi-stage container deployment architecture',
      attempt: 1,
    },
    {
      kind: 'analysis',
      id: uid(),
      title: 'Container Architecture & Service Topology',
      sections: [
        {
          title: 'Services Architecture',
          items: [
            'App Container: Node 20 / Python multi-stage build (distroless/alpine)',
            'Reverse Proxy Container: Nginx Alpine (SSL termination & Gzip compression)',
            'Database Container: PostgreSQL 16 with persistent volume claim',
          ],
        },
        {
          title: 'Networking & Health Checks',
          items: [
            'Internal Bridge Network: backend-net (isolated database communication)',
            'Exposed Ports: 80:80 (HTTP) -> Nginx -> 3000 (Internal App)',
            'Health Check Endpoint: HTTP GET /healthz interval 30s timeout 10s',
          ],
        },
      ],
    },
    {
      kind: 'analysis',
      id: uid(),
      title: 'Target Files, Security & Risk Matrix',
      sections: [
        {
          title: 'Target Manifest Files',
          items: [
            'Dockerfile (Multi-stage builder + Nginx production image)',
            'docker-compose.yml (Multi-container orchestration & network definition)',
            '.dockerignore (Exclude node_modules, .git, and secrets)',
          ],
        },
        {
          title: 'Risks & Mitigation Strategies',
          items: [
            'Risk: Root container vulnerability -> Mitigation: Run as non-root appuser:1000',
            'Risk: Uncached dependency layers -> Mitigation: Separate package.json COPY step',
          ],
        },
      ],
    },
    {
      kind: 'summary',
      id: uid(),
      title: 'Container Architecture Plan Ready',
      description: 'The multi-stage Docker build design and Docker Compose architecture plan have been generated.',
      filesCreated: [],
      commandsExecuted: [
        'docker info',
        'docker compose config (initial discovery)',
      ],
      verified: [
        'Multi-stage layer caching',
        'Docker Compose v3.8 spec',
        'Security & non-root permissions',
        'Health check monitoring',
      ],
    },
    {
      kind: 'planner_action_panel',
      id: uid(),
      defaultFilename: 'implementation-plan.md',
    },
  ],
});
