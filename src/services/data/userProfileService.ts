import fs from 'node:fs';
import path from 'node:path';

export interface UserProfile {
  // Theme & Appearance
  theme: string;
  compactView: boolean;
  thinkingCollapsed: boolean;
  soundEffects: boolean;

  // Session & Execution Controls
  autoApproveTools: boolean;
  persona: string;
  defaultMode: 'build' | 'plan';

  // Session Cache Metadata
  lastActiveWorkspace: string;
  sessionCount: number;
  lastSessionTimestamp: string;
  updatedAt: string;
}

const PROFILE_FILE_NAME = 'user_profile.json';

const DEFAULT_PROFILE: UserProfile = {
  theme: 'graphite',
  compactView: false,
  thinkingCollapsed: false,
  soundEffects: true,
  autoApproveTools: false,
  persona: 'architect',
  defaultMode: 'build',
  lastActiveWorkspace: process.cwd(),
  sessionCount: 1,
  lastSessionTimestamp: new Date().toISOString(),
  updatedAt: new Date().toISOString(),
};

const getProfilePath = (): string => {
  return path.resolve(process.cwd(), PROFILE_FILE_NAME);
};

export const loadUserProfile = (): UserProfile => {
  const filePath = getProfilePath();
  try {
    if (fs.existsSync(filePath)) {
      const rawData = fs.readFileSync(filePath, 'utf-8');
      const parsed = JSON.parse(rawData) as Partial<UserProfile>;
      if (parsed && typeof parsed === 'object') {
        return {
          ...DEFAULT_PROFILE,
          ...parsed,
          sessionCount: (parsed.sessionCount ?? 0) + 1,
          lastSessionTimestamp: new Date().toISOString(),
        };
      }
    }
  } catch (_err) {
    // Fall back to default profile on read failure
  }

  // Create initial user_profile.json file if missing
  saveUserProfile(DEFAULT_PROFILE);
  return DEFAULT_PROFILE;
};

export const saveUserProfile = (updates: Partial<UserProfile>): UserProfile => {
  const filePath = getProfilePath();
  let current: UserProfile = { ...DEFAULT_PROFILE };

  try {
    if (fs.existsSync(filePath)) {
      const rawData = fs.readFileSync(filePath, 'utf-8');
      const parsed = JSON.parse(rawData);
      if (parsed && typeof parsed === 'object') {
        current = { ...current, ...parsed };
      }
    }
  } catch (_err) {
    // Keep base defaults if read fails
  }

  const updatedProfile: UserProfile = {
    ...current,
    ...updates,
    updatedAt: new Date().toISOString(),
  };

  try {
    fs.writeFileSync(filePath, JSON.stringify(updatedProfile, null, 2), 'utf-8');
  } catch (_err) {
    // Ignore write errors in test environments
  }

  return updatedProfile;
};

export const loadSavedTheme = (): string => {
  const profile = loadUserProfile();
  return profile.theme || 'graphite';
};

export const saveTheme = (themeId: string): void => {
  saveUserProfile({ theme: themeId });
};

export const loadAutoApprove = (): boolean => {
  const profile = loadUserProfile();
  return Boolean(profile.autoApproveTools);
};

export const saveAutoApprove = (autoApprove: boolean): void => {
  saveUserProfile({ autoApproveTools: autoApprove });
};
