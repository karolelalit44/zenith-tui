import { Scenario } from '../../../../types/scenario';

let idCounter = 0;
const uid = () => `plan_${Date.now()}_${++idCounter}`;

export const planScenario = (prompt: string): Scenario => ({
  id: `plan_${Date.now()}`,
  mode: 'plan',
  prompt,
  events: [
    {
      kind: 'thinking',
      id: uid(),
      thoughts: [
        { text: `Analyzing user prompt: "${prompt}"`, delay: 250 },
        { text: 'Evaluating system architecture requirements & domain boundaries', delay: 300 },
        { text: 'Formulating step-by-step implementation plan & risk matrix', delay: 300 },
      ],
      duration: 1200,
    },
    {
      kind: 'terminal',
      id: uid(),
      command: 'git status',
      output: [
        'On branch main',
        'Your branch is up to date with "origin/main".',
        'nothing to commit, working tree clean',
      ],
      duration: 400,
    },
    {
      kind: 'analysis',
      id: uid(),
      title: 'Architectural Analysis & System Topology',
      sections: [
        {
          title: 'Proposed Solution Architecture',
          items: [
            'Frontend Layer: React 19 / TypeScript TUI components',
            'Service Layer: ScenarioEngine & StaticContentRepository abstraction',
            'Data Layer: Structured domain events & state management',
          ],
        },
        {
          title: 'Core Requirements & Boundaries',
          items: [
            'Zero-emoji CLI design system with SGR text badges',
            '100% data-driven scenario execution',
            'Touchpad two-finger viewport scrolling support',
          ],
        },
      ],
    },
    {
      kind: 'analysis',
      id: uid(),
      title: 'Target Deliverables, Risk Matrix & Verification',
      sections: [
        {
          title: 'Target Files to Create/Modify',
          items: [
            'src/constants/uiContent.ts (Centralized UI strings)',
            'src/services/data/StaticContentRepository.ts (Static data service)',
            'src/services/data/ScenarioRepository.ts (Scenario repository)',
          ],
        },
        {
          title: 'Risks & Mitigation Strategies',
          items: [
            'Risk: Tight coupling between UI and scenarios -> Mitigation: View Model presenter layer',
            'Risk: Hardcoded text strings -> Mitigation: Centralized UI content repository',
          ],
        },
      ],
    },
    {
      kind: 'summary',
      id: uid(),
      title: 'Implementation Plan Ready',
      description: 'The architectural evaluation and implementation plan have been generated.',
      filesCreated: [],
      commandsExecuted: ['git status'],
      verified: ['System Architecture Analysis', 'File Structure Plan', 'Risk Mitigation Strategy'],
    },
    {
      kind: 'planner_action_panel',
      id: uid(),
      defaultFilename: 'zenith_plans/implementation-plan.md',
    },
  ],
});
