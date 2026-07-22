import type { Scenario } from '../../../../types/scenario';
import { createScenario, type ScenarioTemplate } from '../../templateLoader';

const template: ScenarioTemplate = {
  mode: 'plan',
  events: [
    {
      kind: 'thinking',
      thoughts: [
        { text: 'Analyzing architectural request intent & evaluating workspace file tree AST...', delay: 250 },
        {
          text: 'Inspecting project config files: checking tsconfig.json, package.json, and git working directory status',
          delay: 300,
        },
        {
          text: 'Evaluating system architecture options, module boundaries, data layer contracts, and component modularity',
          delay: 350,
        },
        {
          text: 'Formulating step-by-step implementation roadmap, target file tree, security guardrails, and risk matrix',
          delay: 300,
        },
        { text: 'Preparing markdown plan export payload configuration for zenith_plans/ folder', delay: 250 },
      ],
      duration: 1600,
    },
    {
      kind: 'terminal',
      command: 'git status --porcelain',
      output: [
        'On branch main',
        'Your branch is up to date with "origin/main".',
        'nothing to commit, working tree clean',
      ],
      duration: 400,
    },
    {
      kind: 'terminal',
      command: 'cat package.json | grep -E "name|version|dependencies"',
      output: ['  "name": "zenith-app",', '  "version": "1.0.0",', '  "dependencies": {'],
      duration: 500,
    },
    {
      kind: 'analysis',
      title: 'System Architecture & Implementation Strategy',
      sections: [
        {
          title: '1. Executive Architectural Blueprint',
          items: [
            'System Domain Boundary: Decoupled 4-tier data architecture (UI Layer -> Presenter -> Domain Services -> Repositories)',
            'State & Mutation Strategy: Single source of truth with immutable state updates & reactive event streams',
            'Modular Interface Contracts: Strictly-typed TypeScript interfaces preventing implicit `any` leaks',
          ],
        },
        {
          title: '2. Target Implementation File Tree',
          items: [
            'src/types/domain.ts (Core domain entity contracts & payload types)',
            'src/services/data/DomainRepository.ts (Encapsulated storage & data access layer)',
            'src/components/Display/DomainCard.tsx (UI presentation component with theme token bindings)',
            'tests/domain.test.ts (Vitest unit and integration test assertions)',
          ],
        },
        {
          title: '3. Security, Performance & Risk Matrix',
          items: [
            'Risk: State synchronization overhead -> Mitigation: Memoized selectors & React.memo memoization',
            'Risk: Loose type safety on API boundary -> Mitigation: Zod / Pydantic runtime schema validation',
            'Quality Control: Automated Biome linting, TypeScript compiler checks, and 100% Vitest coverage',
          ],
        },
      ],
    },
    {
      kind: 'summary',
      title: 'Architectural Implementation Plan Ready',
      description:
        'The architectural blueprint, target file tree breakdown, module boundaries, and risk mitigation plan have been generated.',
      filesCreated: [],
      commandsExecuted: ['git status', 'cat package.json'],
      verified: [
        'Decoupled 4-Tier Data Architecture Blueprint',
        'Target File Tree & Module Boundaries',
        'TypeScript Strict Mode Type Guardrails',
        'Vitest Automated Test Strategy & Plan Export',
      ],
    },
    {
      kind: 'planner_action_panel',
      defaultFilename: 'zenith_plans/implementation-plan.md',
      saved: false,
    },
  ],
};

export const planScenario = (prompt: string): Scenario => createScenario(prompt, template);
