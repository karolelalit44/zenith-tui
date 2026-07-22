export interface SessionStatusDefaults {
  maxTokens: number;
  workspaceName: string;
}

export const SESSION_STATUS_DEFAULTS: SessionStatusDefaults = {
  maxTokens: 200000,
  workspaceName: 'zenith-frontend-tui',
};
