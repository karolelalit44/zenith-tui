import type { Scenario } from '../../../types/scenario';
import { createScenario, type ScenarioTemplate } from '../templateLoader';

const template: ScenarioTemplate = {
  mode: 'plan',
  events: [
    {
      kind: 'thinking',
      thoughts: [
        {
          text: 'Analyzing frontend prompt intent: evaluating React 19 architecture, component modularization, and state layer',
          delay: 250,
        },
        {
          text: 'Inspecting workspace repository files, dependencies in package.json, and tsconfig compiler options',
          delay: 300,
        },
        {
          text: 'Evaluating React 19 server components vs client components, Zustand v5 state store, and TanStack Query caching strategy',
          delay: 350,
        },
        {
          text: 'Architecting zero-re-render component hierarchy, route-based code splitting, ARIA accessibility, and security guardrails',
          delay: 300,
        },
        {
          text: 'Formulating comprehensive execution roadmap, file tree breakdown, risk matrix, and plan export configuration',
          delay: 250,
        },
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
      command: 'cat package.json | grep -E "react|vite|zustand|tailwind"',
      output: [
        '  "react": "^19.0.0",',
        '  "react-dom": "^19.0.0",',
        '  "react-router-dom": "^7.0.0",',
        '  "zustand": "^5.0.0"',
      ],
      duration: 500,
    },
    {
      kind: 'analysis',
      title: 'Enterprise React 19 Architecture & State Strategy',
      sections: [
        {
          title: '1. Component Hierarchy & Layout Boundary System',
          items: [
            'Root Application Boundary (App.tsx -> QueryClientProvider -> BrowserRouter -> ThemeProvider)',
            'Layout Layer: DashboardLayout (SidebarNav with active route highlighting, TopHeader with User Menu & Theme Picker)',
            'Reusable UI Token Layer: MetricCard, DataChart (lazy loaded Recharts container), ActionButton, ModalDialog',
            'Page Views: OverviewPage (Key performance metrics & KPI tiles), AnalyticsPage (Interactive charting & timeframe filters)',
          ],
        },
        {
          title: '2. State Management & Data Layer Strategy',
          items: [
            'Global Client State: Zustand v5 store with devtools middleware for user session, active theme, and sidebar collapsed state',
            'Server State & Caching: TanStack Query v5 for API data fetching, background polling, and optimistic UI mutations',
            'Form & Action State: React 19 useActionState and useTransition for non-blocking UI state updates',
          ],
        },
        {
          title: '3. Estimated Target File Tree',
          items: [
            'src/store/useAppStore.ts (Zustand global store)',
            'src/layouts/DashboardLayout.tsx (Root layout container)',
            'src/components/MetricCard.tsx (Reusable metric card component)',
            'src/components/AnalyticsChart.tsx (Lazy-loaded Recharts wrapper)',
            'src/pages/OverviewPage.tsx (Primary dashboard view)',
          ],
        },
        {
          title: '4. Performance, Security & Risk Matrix',
          items: [
            'Risk: Recharts bundle bloat (approx. 320 KB) -> Mitigation: React.lazy dynamic import & Route-level code splitting',
            'Risk: Unnecessary parent-to-child re-renders -> Mitigation: React.memo with shallow Zustand state selectors',
            'Security Guardrail: Enforce Strict Content Security Policy (CSP), sanitize external user inputs with DOMPurify',
          ],
        },
      ],
    },
    {
      kind: 'summary',
      title: 'React 19 Architecture Plan Ready',
      description:
        'The architectural evaluation, state management strategy, file tree breakdown, and risk mitigation plan have been generated.',
      filesCreated: [],
      commandsExecuted: ['git status', 'cat package.json'],
      verified: [
        'React 19 Component Hierarchy & Routing Plan',
        'Zustand v5 Global State & TanStack Query Strategy',
        'Estimated File Structure & Module Boundaries',
        'Performance & Security Risk Mitigation Matrix',
      ],
    },
    {
      kind: 'planner_action_panel',
      defaultFilename: 'zenith_plans/implementation-plan.md',
      saved: false,
    },
  ],
};

export const reactPlanScenario = (prompt: string): Scenario => createScenario(prompt, template);
