import type { Persona } from '../../../types';

export const WELCOME_DATA = {
  title: 'ZENITH',
  version: 'v1.0.0',
  systemStatus: {
    label: 'SYSTEM STATUS',
    engineLabel: 'Engine: ',
    personaLabel: 'Persona: ',
    workspaceLabel: 'Workspace: ',
  },
} as const;

export const getGreeting = (persona: Persona): string => {
  switch (persona) {
    case 'debugger':
      return 'Inspecting tracebacks & stack traces...';
    case 'creative':
      return 'Crafting elegant UI/UX design systems...';
    default:
      return 'Designing scalable system architecture...';
  }
};
