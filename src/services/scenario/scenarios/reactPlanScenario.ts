import { Scenario } from '../../../types/scenario';

let idCounter = 0;
const uid = () => `plan_react_${++idCounter}`;

export const reactPlanScenario = (prompt: string): Scenario => ({
  id: `plan_react_${Date.now()}`,
  mode: 'plan',
  prompt,
  events: [
    {
      kind: 'thinking',
      id: uid(),
      thoughts: [
        { text: 'Analyzing frontend requirements', delay: 300 },
        { text: 'Identifying component hierarchy', delay: 400 },
        { text: 'Evaluating state management needs', delay: 350 },
        { text: 'Assessing routing structure', delay: 300 },
      ],
      duration: 1500,
    },
    {
      kind: 'analysis',
      id: uid(),
      title: 'Frontend Architecture',
      sections: [
        {
          title: 'Component Tree',
          items: [
            'App → Layout → Pages → Components',
            'Shared UI components (Button, Card, Modal)',
            'Feature-specific components (Dashboard, Settings)',
            'Layout wrappers (Header, Sidebar, Footer)',
          ],
        },
        {
          title: 'State Management',
          items: [
            'Global: Zustand or React Context',
            'Server: React Query / SWR',
            'Local: useState / useReducer',
            'Form: React Hook Form',
          ],
        },
      ],
    },
    {
      kind: 'thinking',
      id: uid(),
      thoughts: [
        { text: 'Planning data fetching strategy', delay: 350 },
        { text: 'Designing responsive layout approach', delay: 300 },
        { text: 'Evaluating performance optimization', delay: 400 },
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
            '15-20 component files',
            '5-8 page files',
            '3-5 hook files',
            '4-6 configuration files',
          ],
        },
        {
          title: 'Dependencies',
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
            'Bundle size optimization',
            'Accessibility compliance',
            'Cross-browser compatibility',
          ],
        },
      ],
    },
    {
      kind: 'message',
      id: uid(),
      text: 'Frontend architecture analysis complete. Switch to Build mode to implement.',
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
