export interface SessionStatusDefaults {
  maxTokens: number;
  workspaceName: string;
}

const WORKSPACE_NAME_DEFAULT = process.cwd().split(/[\\/]/).filter(Boolean).pop() ?? 'zenith';

export const SESSION_STATUS_DEFAULTS: SessionStatusDefaults = {
  maxTokens: 200000,
  workspaceName: WORKSPACE_NAME_DEFAULT,
};
