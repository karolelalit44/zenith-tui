export interface DiffSegment {
  text: string;
  isHighlightedWord?: boolean;
}

export interface DiffLine {
  type: 'add' | 'remove' | 'context';
  number: number;
  segments: DiffSegment[];
}

export type Persona = 'architect' | 'debugger' | 'creative';

export type LogItem =
  | { type: 'user'; text: string }
  | { type: 'text'; text: string }
  | { type: 'add-dir'; path: string }
  | { type: 'tool'; name: string; args: string; resultTitle: string; diff?: DiffLine[] };

export interface CommandHint {
  command: string;
  description: string;
}
