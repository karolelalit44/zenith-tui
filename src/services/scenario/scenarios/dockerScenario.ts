import type { Scenario } from '../../../types/scenario';
import { createScenario, type ScenarioTemplate } from '../templateLoader';

const template: ScenarioTemplate = {
  mode: 'build',
  events: [
    {
      kind: 'thinking',
      thoughts: [
        {
          text: 'Inspecting workspace layout and detecting multi-stage Docker build target requirement...',
          delay: 250,
        },
        {
          text: 'Evaluating security hardening: non-root user (UID 10001), read-only root filesystem, drop ALL Linux capabilities',
          delay: 300,
        },
        {
          text: 'Architecting 2-stage build: node:22-alpine build container → nginx:1.27-alpine-slim production runtime',
          delay: 350,
        },
        {
          text: 'Configuring Trivy vulnerability scanning, Docker Buildx cache mounts, and healthcheck probe endpoints',
          delay: 300,
        },
      ],
      duration: 1500,
    },
    {
      kind: 'terminal',
      command: 'docker info && docker buildx version',
      output: [
        'Client: Docker Engine - Community (v27.1.1)',
        'Server: Engine v27.1.1 (platform linux/amd64)',
        'github.com/docker/buildx v0.16.1',
        '✓ Buildx container driver ready',
      ],
      duration: 1000,
    },
    {
      kind: 'file_create',
      filePath: 'Dockerfile',
      directory: './',
      language: 'dockerfile',
      lines: [
        { text: '# Stage 1: Build & Type Check', type: 'add' },
        { text: 'FROM node:22-alpine AS builder', type: 'add' },
        { text: 'WORKDIR /app', type: 'add' },
        { text: 'COPY package*.json ./', type: 'add' },
        { text: 'RUN --mount=type=cache,target=/root/.npm npm ci --prefer-offline', type: 'add' },
        { text: 'COPY . .', type: 'add' },
        { text: 'RUN npm run build', type: 'add' },
        { text: '', type: 'add' },
        { text: '# Stage 2: Hardened Runtime Environment', type: 'add' },
        { text: 'FROM nginx:1.27-alpine-slim AS runner', type: 'add' },
        { text: 'RUN addgroup -g 10001 -S zenith && adduser -u 10001 -S zenith -G zenith', type: 'add' },
        { text: 'COPY nginx.conf /etc/nginx/nginx.conf', type: 'add' },
        { text: 'COPY --from=builder /app/dist /usr/share/nginx/html', type: 'add' },
        { text: 'RUN chown -R zenith:zenith /usr/share/nginx/html /var/cache/nginx /var/log/nginx', type: 'add' },
        { text: 'USER zenith', type: 'add' },
        { text: 'EXPOSE 8080', type: 'add' },
        {
          text: 'HEALTHCHECK --interval=15s --timeout=3s CMD wget --quiet --tries=1 --spider http://localhost:8080/health || exit 1',
          type: 'add',
        },
        { text: 'CMD ["nginx", "-g", "daemon off;"]', type: 'add' },
      ],
    },
    {
      kind: 'file_create',
      filePath: 'docker-compose.yml',
      directory: './',
      language: 'yaml',
      lines: [
        { text: 'name: zenith-stack', type: 'add' },
        { text: 'services:', type: 'add' },
        { text: '  web:', type: 'add' },
        { text: '    build:', type: 'add' },
        { text: '      context: .', type: 'add' },
        { text: '      dockerfile: Dockerfile', type: 'add' },
        { text: '    ports:', type: 'add' },
        { text: '      - "8080:8080"', type: 'add' },
        { text: '    security_opt:', type: 'add' },
        { text: '      - no-new-privileges:true', type: 'add' },
        { text: '    read_only: true', type: 'add' },
        { text: '    tmpfs:', type: 'add' },
        { text: '      - /tmp', type: 'add' },
        { text: '      - /var/cache/nginx', type: 'add' },
        { text: '      - /var/run', type: 'add' },
        { text: '    restart: unless-stopped', type: 'add' },
      ],
    },
    {
      kind: 'build_step',
      step: 'Docker Buildx Image Assembly ($ docker buildx build -t zenith-app:v1.0.0 .)',
      status: 'success',
      duration: 1800,
      output: [
        '[1/2] FROM node:22-alpine AS builder (CACHED)',
        '[2/2] FROM nginx:1.27-alpine-slim AS runner',
        'exporting image to docker engine...',
        '✓ Image assembled cleanly: 28.4 MB (reduced from 412 MB)',
      ],
    },
    {
      kind: 'terminal',
      command:
        'docker run --rm -d --name test-zenith -p 8080:8080 zenith-app:v1.0.0 && sleep 2 && curl -I http://localhost:8080/health',
      output: [
        'a8f9e0c12d4b56789e0123456789abcdef0123456789abcdef0123456789abcdef',
        'HTTP/1.1 200 OK',
        'Server: nginx/1.27.0',
        'Content-Type: text/plain',
        '✓ Container healthcheck probe responded 200 OK',
      ],
      duration: 1600,
    },
    {
      kind: 'summary',
      title: 'Hardened Multi-Stage Docker Container Assembled',
      description:
        'Built production 2-stage Docker container with non-root security (UID 10001), read-only rootfs, healthcheck probe, and 28.4 MB total image footprint.',
      filesCreated: ['Dockerfile', 'docker-compose.yml'],
      commandsExecuted: [
        'docker info',
        'docker buildx build -t zenith-app:v1.0.0 .',
        'docker run --rm -d -p 8080:8080 zenith-app:v1.0.0',
        'curl -I http://localhost:8080/health',
      ],
      verified: [
        'Multi-Stage Build (Node 22 Builder -> Nginx Alpine Slim Runner)',
        'Non-Root Security Hardening (UID 10001 zenith)',
        'Read-Only Root Filesystem & Tmpfs Mounts',
        'Healthcheck Probe Endpoint (200 OK)',
      ],
    },
  ],
};

export const dockerScenario = (prompt: string): Scenario => createScenario(prompt, template);
