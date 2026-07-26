let profileCache: UserProfile | null = null;

interface UserProviderSection {
  activeProvider: string;
  activeModel: string;
}

interface UserSettingsSection {
  theme: string;
  thinkingCollapsed: boolean;
  autoApproveTools: boolean;
  defaultMode: 'build' | 'plan';
}

export interface UserProfile {
  provider: UserProviderSection;
  settings: UserSettingsSection;
  providerSettings?: Record<string, unknown>;
  lastActiveWorkspace: string;
  sessionCount: number;
  lastSessionTimestamp: string;
  updatedAt: string;
}

const DEFAULT_THEME = 'graphite';
const DEFAULT_MODE = 'build' as const;

function getInitialProfile(): UserProfile {
  return {
    provider: {
      activeProvider: '',
      activeModel: '',
    },
    settings: {
      theme: DEFAULT_THEME,
      thinkingCollapsed: false,
      autoApproveTools: false,
      defaultMode: DEFAULT_MODE,
    },
    providerSettings: {},
    lastActiveWorkspace: process.cwd(),
    sessionCount: 1,
    lastSessionTimestamp: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  };
}

export const loadUserProfile = (): UserProfile => {
  if (profileCache) return profileCache;
  profileCache = getInitialProfile();
  return profileCache;
};

export const saveUserProfile = (updates: Partial<UserProfile>): UserProfile => {
  const current = loadUserProfile();

  const updatedProfile: UserProfile = {
    ...current,
    ...updates,
    provider: updates.provider
      ? { ...current.provider, ...updates.provider }
      : current.provider,
    settings: updates.settings
      ? { ...current.settings, ...updates.settings }
      : current.settings,
    updatedAt: new Date().toISOString(),
  };

  profileCache = updatedProfile;
  return updatedProfile;
};
