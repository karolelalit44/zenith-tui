import { Persona } from '../../../types';

export const WELCOME_DATA = {
  title: 'ZENITH',
  version: 'v1.0.0',
  systemStatus: {
    label: 'SYSTEM STATUS',
    engineLabel: 'Engine: ',
    personaLabel: 'Persona: ',
    workspaceLabel: 'Workspace: ',
  },
  recentSessions: [
    {
      time: '[ 21:03, 20 July ]',
      title: 'Refactored authentication flow',
      persona: 'Architect' as const,
    },
  ],
} as const;

export const getGreeting = (persona: Persona): string => {
  const hour = new Date().getHours();
  if (hour >= 5 && hour < 12) return 'Compiling coffee...';
  if (hour >= 12 && hour < 17) return 'Midday grind.';
  if (hour >= 17 && hour < 22) return 'Sun is down, screens are bright.';
  return 'Burning the midnight oil, John Doe?';
};
