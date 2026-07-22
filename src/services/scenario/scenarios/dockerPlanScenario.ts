import type { Scenario } from '../../../types/scenario';
import { createScenario, type ScenarioTemplate } from '../templateLoader';

const template: ScenarioTemplate = {
  mode: 'plan',
  events: [
    {
      kind: 'thinking',
      thoughts: [
        {
          text: 'Analyzing containerization prompt intent: evaluating Docker multi-stage build & security profile',
          delay: 250,
        },
        {
          text: 'Inspecting workspace layout, build artifacts, node_modules dependencies, and asset footprint',
          delay: 300,
        },
        {
          text: 'Architecting 2-stage build: node:22-alpine compilation → nginx:1.27-alpine-slim minimal runtime',
          delay: 350,
        },
        {
          text: 'Formulating security hardening: non-root user (UID 10001), read-only rootfs, tmpfs mounts, drop Linux capabilities',
          delay: 300,
        },
        {
          text: 'Designing Trivy vulnerability scanner integration, Buildx cache mounts, and Docker Compose orchestration',
          delay: 250,
        },
      ],
      duration: 1600,
    },
    {
      kind: 'terminal',
      command: 'docker --version && docker buildx version',
      output: ['Docker version 27.1.1, build 6312585', 'github.com/docker/buildx v0.16.1'],
      duration: 400,
    },
    {
      kind: 'analysis',
      title: 'Containerization & Docker Security Strategy',
      sections: [
        {
          title: '1. Multi-Stage Build Architecture',
          items: [
            'Stage 1 (Builder): node:22-alpine container installing npm dependencies with cache mounts & compiling dist/',
            'Stage 2 (Runtime): nginx:1.27-alpine-slim minimal base image containing only compiled dist assets',
            'Image Size Reduction: Target image footprint reduced from 412 MB -> ~28 MB',
          ],
        },
        {
          title: '2. Security Hardening & Isolation Profile',
          items: [
            'Non-Root User: Dedicated unprivileged system user `zenith` (UID 10001 / GID 10001)',
            'Read-Only Root Filesystem: `read_only: true` with ephemeral `tmpfs` mounts for `/tmp` & `/var/cache/nginx`',
            'Capabilities: Drop ALL Linux capabilities (`cap_drop: [ALL]`), disable privilege escalation (`no-new-privileges: true`)',
          ],
        },
        {
          title: '3. Target Configuration Files',
          items: [
            'Dockerfile (Multi-stage build assembly)',
            'docker-compose.yml (Orchestration & security runtime specs)',
            'nginx.conf (Gzip compression, security headers, SPA fallback routing)',
            '.dockerignore (Exclude node_modules, .git, .env, coverage reports)',
          ],
        },
        {
          title: '4. Healthcheck & Inspection Roadmap',
          items: [
            'Health Check Probe: HTTP GET `http://localhost:8080/health` (15s interval, 3s timeout)',
            'Vulnerability Scanning: Trivy container image scan (`trivy image zenith-app:v1.0.0`) in CI pipeline',
          ],
        },
      ],
    },
    {
      kind: 'summary',
      title: 'Docker Security & Build Architecture Plan Ready',
      description:
        'The multi-stage build design, non-root security profile, container configuration breakdown, and healthcheck roadmap have been generated.',
      filesCreated: [],
      commandsExecuted: ['docker --version'],
      verified: [
        'Multi-Stage Build Pipeline Design (Node -> Nginx Alpine)',
        'Container Security Profile (Non-root UID 10001 & Read-Only Rootfs)',
        'Target File Breakdown (Dockerfile, docker-compose.yml, nginx.conf)',
        'Trivy Security Scanning & Healthcheck Probe Strategy',
      ],
    },
    {
      kind: 'planner_action_panel',
      defaultFilename: 'zenith_plans/implementation-plan.md',
      saved: false,
    },
  ],
};

export const dockerPlanScenario = (prompt: string): Scenario => createScenario(prompt, template);
