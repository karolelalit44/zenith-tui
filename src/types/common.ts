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

export interface OutputMeta {
  kind: 'file_edit' | 'file_created' | 'file_deleted' | 'message' | 'build_result' | 'tool_result' | 'error';
  icon: string;
  title: string;
  status: 'success' | 'warning' | 'error' | 'info';
  filePath?: string;
  message?: string;
  diff?: DiffLine[];
  buildSteps?: { label: string; duration: string; success: boolean }[];
  elapsed?: string;
}

export type LogItem =
  | { type: 'user'; text: string }
  | { type: 'output'; meta: OutputMeta };

export interface CommandHint {
  command: string;
  description: string;
}

export type ThinkingPhase = 'thinking' | 'analyzing' | 'tool_use' | 'compiling' | 'scanning' | 'fetching' | 'building' | 'idle';

export interface ThinkingStep {
  label: string;
}

export interface ThinkingState {
  isActive: boolean;
  phase: ThinkingPhase;
  message: string;
  steps: ThinkingStep[];
  currentStepIndex: number;
}
