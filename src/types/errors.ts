export type ErrorCategory = 'provider' | 'system' | 'validation' | 'mode_mismatch' | 'capability';

export interface ErrorDefinition {
  category: ErrorCategory;
  code: string;
  title: string;
  description: string;
  cause?: string;
  recommendedAction: string;
  canRetry: boolean;
  docUrl?: string;
}

export interface WarningDefinition {
  code: string;
  title: string;
  description: string;
  impact: string;
  actionRequired: boolean;
}

export interface ModeMismatchDefinition {
  currentMode: 'plan' | 'build';
  suggestedMode: 'plan' | 'build';
  reason: string;
  shortcutHint: string;
}

export interface EmptyStateDefinition {
  title: string;
  description: string;
  suggestedActions: string[];
}
