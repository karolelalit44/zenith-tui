import { Persona } from '../../../../types';

export interface PersonaOption {
  id: Persona;
  label: string;
  icon: string;
  desc: string;
}

export const PERSONA_OPTIONS: PersonaOption[] = [
  { id: 'architect', label: 'The Architect', icon: '◩', desc: 'Default logic and balanced code generation.' },
  { id: 'debugger', label: 'The Debugger', icon: '⯈', desc: 'Hyper-focused on stack traces and bug hunting.' },
  { id: 'creative', label: 'The Creative', icon: '✧', desc: 'Optimized for UI/UX design and aesthetic styling.' },
];

export const ACCOUNT_META = {
  title: 'Select Persona',
  headerLabel: 'CONFIGURE SYSTEM PERSONA',
  activeBadge: '● ACTIVE',
  hotkeys: {
    navigate: '[↑↓] Navigate',
    select: '[↵] Select',
    close: '[Esc] Close',
  },
} as const;
