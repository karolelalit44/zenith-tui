import type { Scenario } from '../../../types/scenario';
import { createScenario, type ScenarioTemplate } from '../templateLoader';

const buildTemplate = (prompt: string): ScenarioTemplate => ({
  mode: 'plan',
  events: [
    {
      kind: 'thinking',
      thoughts: [
        { text: `Analyzing React/Frontend prompt: "${prompt}"`, delay: 250 },
        { text: 'Evaluating React 19 component hierarchy & state management model', delay: 300 },
        { text: 'Planning responsive layout approach & routing structure', delay: 300 },
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
      command: 'npx check-workspace --template react',
      output: ['Error: Could not locate workspace configuration manifest.', 'MISSING_MANIFEST: ./react-workspace.json'],
      duration: 500,
    },
    {
      kind: 'thinking',
      thoughts: [
        { text: 'Detected missing workspace configuration manifest', delay: 300 },
        { text: 'Switching to fallback inspection: parsing package.json for React & Vite', delay: 300 },
      ],
      duration: 1000,
    },
    {
      kind: 'retry',
      message: 'Retrying workspace discovery using fallback package inspection',
      attempt: 2,
    },
    {
      kind: 'terminal',
      command: 'cat package.json | grep -E "react|vite|recharts|zustand"',
      output: [
        '  "react": "^19.0.0",',
        '  "react-dom": "^19.0.0",',
        '  "recharts": "^2.12.0",',
        '  "zustand": "^4.5.0"',
      ],
      duration: 450,
    },
    {
      kind: 'analysis',
      title: 'Frontend Component Architecture & State Strategy',
      sections: [
        {
          title: 'Component Hierarchy',
          items: [
            'App → BrowserRouter → DashboardLayout → (OverviewPage | AnalyticsPage)',
            'Reusable UI Layer: MetricCard, DataChart, NavigationSidebar',
            'Layout Layer: Header (User Profile, Theme Toggle), Sidebar Navigation',
            'Page Layer: OverviewPage (Key Metrics), AnalyticsPage (Recharts Visualizations)',
          ],
        },
        {
          title: 'State & Data Layer Strategy',
          items: [
            'Global Application State: Zustand store (user session, theme, workspace settings)',
            'Server Data Fetching: React Query / TanStack Query with optimistic updates',
            'Local Form & UI State: React 19 useState / useActionState',
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
            'dashboard/src/App.tsx (Routing & global providers)',
            'dashboard/src/layouts/DashboardLayout.tsx (Sidebar & Topbar)',
            'dashboard/src/components/MetricCard.tsx (Reusable metric tile)',
            'dashboard/src/pages/OverviewPage.tsx (Recharts dashboard page)',
          ],
        },
        {
          title: 'Risks & Mitigation Strategies',
          items: [
            'Risk: Recharts bundle size bloat -> Mitigation: Dynamic import / code splitting',
            'Risk: Excessive re-renders on layout updates -> Mitigation: Zustand memoized selectors',
          ],
        },
      ],
    },
    {
      kind: 'summary',
      title: 'React Architecture Plan Ready',
      description: 'The component hierarchy, state management design, and file tree plan have been generated.',
      filesCreated: [],
      commandsExecuted: ['git status', 'npx check-workspace (fallback recovered)', 'cat package.json'],
      verified: [
        'React 19 Component Architecture',
        'Zustand State Strategy',
        'File Structure Breakdown',
        'Risk Mitigation Strategy',
      ],
    },
    {
      kind: 'planner_action_panel',
      defaultFilename: 'implementation-plan.md',
    },
  ],
});

export const reactPlanScenario = (prompt: string): Scenario => createScenario(prompt, buildTemplate(prompt));
