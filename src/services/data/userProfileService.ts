import fs from 'node:fs';
import path from 'node:path';

let profileCache: UserProfile | null = null;
const CACHE_TTL = 5000;
let cacheTimestamp = 0;

export interface UserProviderSection {
  activeProvider: string;
  activeModel: string;
}

export interface UserSettingsSection {
  theme: string;
  compactView: boolean;
  thinkingCollapsed: boolean;
  soundEffects: boolean;
  autoApproveTools: boolean;
  persona: string;
  defaultMode: 'build' | 'plan';
}

export interface UserProfile {
  // Nested configuration blocks
  provider?: UserProviderSection;
  settings?: UserSettingsSection;
  providerSettings?: Record<string, unknown>;

  // Flat fallbacks / legacy compatibility
  theme: string;
  compactView: boolean;
  thinkingCollapsed: boolean;
  soundEffects: boolean;
  autoApproveTools: boolean;
  persona: string;
  defaultMode: 'build' | 'plan';
  activeProvider?: string;
  activeModel?: string;

  // Session Cache Metadata
  lastActiveWorkspace: string;
  sessionCount: number;
  lastSessionTimestamp: string;
  updatedAt: string;
}

const PROFILE_FILE_NAME = 'user_profile.json';

const DEFAULT_PROFILE: UserProfile = {
  provider: {
    activeProvider: 'openai',
    activeModel: 'gpt-4o',
  },
  settings: {
    theme: 'graphite',
    compactView: false,
    thinkingCollapsed: false,
    soundEffects: true,
    autoApproveTools: false,
    persona: 'architect',
    defaultMode: 'build',
  },
  providerSettings: {},

  // Legacy flat fields synced with nested blocks
  activeProvider: 'openai',
  activeModel: 'gpt-4o',
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
  const now = Date.now();
  if (profileCache && now - cacheTimestamp < CACHE_TTL) return profileCache;

  const filePath = getProfilePath();
  try {
    if (fs.existsSync(filePath)) {
      const rawData = fs.readFileSync(filePath, 'utf-8');
      const parsed = JSON.parse(rawData) as Partial<UserProfile>;
      if (parsed && typeof parsed === 'object') {
        const activeProv = parsed.provider?.activeProvider || parsed.activeProvider || 'openai';
        const activeMod = parsed.provider?.activeModel || parsed.activeModel || 'gpt-4o';
        const themeVal = parsed.settings?.theme || parsed.theme || 'graphite';
        const personaVal = parsed.settings?.persona || parsed.persona || 'architect';

        profileCache = {
          ...DEFAULT_PROFILE,
          ...parsed,
          activeProvider: activeProv,
          activeModel: activeMod,
          theme: themeVal,
          persona: personaVal,
          provider: {
            activeProvider: activeProv,
            activeModel: activeMod,
          },
          settings: {
            theme: themeVal,
            compactView: parsed.settings?.compactView ?? parsed.compactView ?? false,
            thinkingCollapsed: parsed.settings?.thinkingCollapsed ?? parsed.thinkingCollapsed ?? false,
            soundEffects: parsed.settings?.soundEffects ?? parsed.soundEffects ?? true,
            autoApproveTools: parsed.settings?.autoApproveTools ?? parsed.autoApproveTools ?? false,
            persona: personaVal,
            defaultMode: parsed.settings?.defaultMode || parsed.defaultMode || 'build',
          },
          sessionCount: (parsed.sessionCount ?? 0) + 1,
          lastSessionTimestamp: new Date().toISOString(),
        };
        cacheTimestamp = now;
        return profileCache;
      }
    }
  } catch (_err) {
    // Fall back to default profile
  }

  saveUserProfile(DEFAULT_PROFILE);
  profileCache = DEFAULT_PROFILE;
  cacheTimestamp = Date.now();
  return DEFAULT_PROFILE;
};

export const saveUserProfile = (updates: Partial<UserProfile>): UserProfile => {
  profileCache = null;
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
    // Keep base defaults
  }

  const newActiveProvider =
    updates.activeProvider || updates.provider?.activeProvider || current.activeProvider || 'openai';
  const newActiveModel = updates.activeModel || updates.provider?.activeModel || current.activeModel || 'gpt-4o';
  const newTheme = updates.theme || updates.settings?.theme || current.theme || 'graphite';

  const updatedProfile: UserProfile = {
    ...current,
    ...updates,
    activeProvider: newActiveProvider,
    activeModel: newActiveModel,
    theme: newTheme,
    provider: {
      activeProvider: newActiveProvider,
      activeModel: newActiveModel,
    },
    settings: {
      theme: newTheme,
      compactView:
        updates.settings?.compactView ??
        updates.compactView ??
        current.settings?.compactView ??
        current.compactView ??
        false,
      thinkingCollapsed:
        updates.settings?.thinkingCollapsed ??
        updates.thinkingCollapsed ??
        current.settings?.thinkingCollapsed ??
        current.thinkingCollapsed ??
        false,
      soundEffects:
        updates.settings?.soundEffects ??
        updates.soundEffects ??
        current.settings?.soundEffects ??
        current.soundEffects ??
        true,
      autoApproveTools:
        updates.settings?.autoApproveTools ??
        updates.autoApproveTools ??
        current.settings?.autoApproveTools ??
        current.autoApproveTools ??
        false,
      persona:
        updates.settings?.persona || updates.persona || current.settings?.persona || current.persona || 'architect',
      defaultMode:
        updates.settings?.defaultMode ||
        updates.defaultMode ||
        current.settings?.defaultMode ||
        current.defaultMode ||
        'build',
    },
    updatedAt: new Date().toISOString(),
  };

  try {
    fs.writeFileSync(filePath, JSON.stringify(updatedProfile, null, 2), 'utf-8');
  } catch (_err) {
    // Ignore write errors
  }

  return updatedProfile;
};

export const loadSavedTheme = (): string => {
  const profile = loadUserProfile();
  return profile.settings?.theme || profile.theme || 'graphite';
};

export const saveTheme = (themeId: string): void => {
  saveUserProfile({ theme: themeId });
};

export const loadAutoApprove = (): boolean => {
  const profile = loadUserProfile();
  return Boolean(profile.settings?.autoApproveTools ?? profile.autoApproveTools);
};

export const saveAutoApprove = (autoApprove: boolean): void => {
  saveUserProfile({ autoApproveTools: autoApprove });
};
