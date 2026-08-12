import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';

let profileCache: UserProfile | null = null;

const PROFILE_DIR = path.join(os.homedir(), '.zenith');
const PROFILE_PATH = path.join(PROFILE_DIR, 'profile.json');

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

function ensureDir(): void {
  try {
    if (!fs.existsSync(PROFILE_DIR)) {
      fs.mkdirSync(PROFILE_DIR, { recursive: true });
    }
  } catch {}
}

function readFromDisk(): UserProfile | null {
  try {
    ensureDir();
    if (fs.existsSync(PROFILE_PATH)) {
      const raw = fs.readFileSync(PROFILE_PATH, 'utf-8');
      const parsed = JSON.parse(raw);
      if (parsed && typeof parsed === 'object' && parsed.settings) {
        return parsed as UserProfile;
      }
    }
  } catch {}
  return null;
}

function writeToDisk(profile: UserProfile): void {
  try {
    ensureDir();
    fs.writeFileSync(PROFILE_PATH, JSON.stringify(profile, null, 2), 'utf-8');
  } catch {}
}

let saveTimer: ReturnType<typeof setTimeout> | null = null;

function debouncedSave(profile: UserProfile): void {
  if (saveTimer) clearTimeout(saveTimer);
  saveTimer = setTimeout(() => writeToDisk(profile), 500);
}

export const loadUserProfile = (): UserProfile => {
  if (profileCache) return profileCache;
  profileCache = readFromDisk() || getInitialProfile();
  return profileCache;
};

export const saveUserProfile = (updates: Partial<UserProfile>): UserProfile => {
  const current = loadUserProfile();

  const updatedProfile: UserProfile = {
    ...current,
    ...updates,
    provider: updates.provider ? { ...current.provider, ...updates.provider } : current.provider,
    settings: updates.settings ? { ...current.settings, ...updates.settings } : current.settings,
    updatedAt: new Date().toISOString(),
  };

  profileCache = updatedProfile;
  debouncedSave(updatedProfile);
  return updatedProfile;
};
