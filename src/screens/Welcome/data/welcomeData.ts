import { APP_VERSION } from '../../../constants/app';
import type { Persona } from '../../../types';

export const WELCOME_DATA = {
  title: 'ZENITH',
  version: `v${APP_VERSION}`,
  systemStatus: {
    label: 'SYSTEM STATUS',
    engineLabel: 'Engine: ',
    personaLabel: 'Persona: ',
    workspaceLabel: 'Workspace: ',
  },
} as const;

function getTimeOfDay(): string {
  const hour = new Date().getHours();
  if (hour < 12) return 'Morning';
  if (hour < 18) return 'Afternoon';
  return 'Evening';
}

function getPersonaMission(persona: Persona): string {
  switch (persona) {
    case 'debugger':
      return 'Inspecting tracebacks & stack traces...';
    case 'creative':
      return 'Crafting elegant UI/UX design systems...';
    default:
      return 'Designing scalable system architecture...';
  }
}

function getSystemUsername(): string {
  return process.env.USERNAME || process.env.USER || 'Operator';
}

export const getGreeting = (persona: Persona): string => {
  const username = getSystemUsername();
  const timeOfDay = getTimeOfDay();
  const mission = getPersonaMission(persona);
  return `▸ Good ${timeOfDay}, ${username} ◂\n${mission}`;
};
