export type ThinkingPhase = 'thinking' | 'analyzing' | 'tool_use' | 'compiling' | 'scanning' | 'fetching' | 'building' | 'idle';

export interface ThinkingStep {
  label: string;
  icon?: string;
}

export interface ThinkingIndicatorProps {
  phase: ThinkingPhase;
  message: string;
  steps?: ThinkingStep[];
  currentStepIndex?: number;
  showElapsed?: boolean;
  compact?: boolean;
}

export interface ThinkingTimerProps {
  isActive: boolean;
}
