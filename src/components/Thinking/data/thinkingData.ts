import { ThinkingPhase } from '../types';

export const PHASE_META: Record<ThinkingPhase, { icon: string; label: string; colorKey: 'emerald' | 'warning' | 'ethereal' | 'error' }> = {
  idle:      { icon: '○', label: 'Idle',          colorKey: 'muted' as never },
  thinking:  { icon: '◈', label: 'Thinking',     colorKey: 'emerald' },
  analyzing: { icon: '◇', label: 'Analyzing',    colorKey: 'emerald' },
  tool_use:  { icon: '◆', label: 'Using Tool',   colorKey: 'warning' },
  compiling: { icon: '⬡', label: 'Compiling',    colorKey: 'warning' },
  scanning:  { icon: '◎', label: 'Scanning',     colorKey: 'emerald' },
  fetching:  { icon: '◌', label: 'Fetching',     colorKey: 'emerald' },
  building:  { icon: '⬢', label: 'Building',     colorKey: 'warning' },
};

export const THINKING_PHRASES = [
  'Processing request...',
  'Evaluating constraints...',
  'Mapping dependencies...',
  'Optimizing approach...',
  'Synthesizing solution...',
] as const;

export const INTERRUPT_HINT = 'esc to interrupt';
