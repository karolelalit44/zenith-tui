import { appConfig } from '../../config/appConfig';
import type { PermissionLevel, PermissionScope } from '../../types/scenario';
import { resolveWorkspaceRoot } from '../../utils/workspacePath';

/**
 * User profile access — server-owned since the database removal.
 *
 * The canonical profile lives in `<ZENITH_HOME>/user_profile.json` and is
 * owned by the backend. The TUI reads it through `GET /profile` (masked)
 * and writes preference changes through `PUT /profile/preferences`.
 * A synchronous in-memory cache keeps the render-path API unchanged.
 *
 * Hydration retries with a fixed delay until the backend answers (or the
 * attempt cap is hit), so a backend that starts after the TUI still wins
 * eventual consistency. Settings changed locally but not yet confirmed
 * persisted (`pendingSettingKeys`) are never overwritten by a late
 * hydration response — the debounced save re-persists them instead.
 */

interface UserProviderSection {
  activeProvider: string;
  activeModel: string;
}

interface UserSettingsSection {
  theme: string;
  thinkingCollapsed: boolean;
  /** Calm mode (/clam): when true, model thinking output is hidden entirely. */
  calmMode: boolean;
  /** Per-scope permission level; server-owned default mirrors DEFAULT_PERMISSION_POLICY. */
  permissionPolicy: Partial<Record<PermissionScope, PermissionLevel>>;
  defaultMode: 'build' | 'plan';
}

export type { PermissionLevel, PermissionScope };

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

const DEFAULT_PERMISSION_POLICY: Partial<Record<PermissionScope, PermissionLevel>> = {
  read: 'allow',
  write: 'allow',
  delete: 'ask',
  command: 'ask',
  network: 'ask',
  crewmate: 'ask',
  plan: 'ask',
};

const VALID_LEVELS: readonly PermissionLevel[] = ['ask', 'allow', 'deny'];

function sanitizePermissionPolicy(value: unknown): Partial<Record<PermissionScope, PermissionLevel>> {
  const out: Partial<Record<PermissionScope, PermissionLevel>> = {};
  if (value && typeof value === 'object') {
    for (const [scope, level] of Object.entries(value as Record<string, unknown>)) {
      if (VALID_LEVELS.includes(level as PermissionLevel)) {
        out[scope as PermissionScope] = level as PermissionLevel;
      }
    }
  }
  return out;
}

const HYDRATE_MAX_ATTEMPTS = 0;
const HYDRATE_RETRY_MS = 1000;

let profileCache: UserProfile = getInitialProfile();
let hydrated = false;
let hydrateAttempts = 0;
let hydrateTimer: ReturnType<typeof setTimeout> | null = null;
let saveTimer: ReturnType<typeof setTimeout> | null = null;
const hydrationListeners: Array<(p: UserProfile) => void> = [];
const pendingSettingKeys = new Set<string>();

function getInitialProfile(): UserProfile {
  return {
    provider: {
      activeProvider: '',
      activeModel: '',
    },
    settings: {
      theme: DEFAULT_THEME,
      thinkingCollapsed: false,
      calmMode: false,
      permissionPolicy: { ...DEFAULT_PERMISSION_POLICY },
      defaultMode: DEFAULT_MODE,
    },
    providerSettings: {},
    lastActiveWorkspace: resolveWorkspaceRoot(),
    sessionCount: 1,
    lastSessionTimestamp: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  };
}

function applyServerPayload(payload: Record<string, unknown>): void {
  const prefs = (payload.preferences ?? {}) as Record<string, unknown>;
  const nextSettings: UserSettingsSection = { ...profileCache.settings };
  if (!pendingSettingKeys.has('theme') && typeof prefs.theme === 'string' && prefs.theme) {
    nextSettings.theme = prefs.theme;
  }
  if (!pendingSettingKeys.has('thinkingCollapsed') && typeof prefs.thinkingCollapsed === 'boolean') {
    nextSettings.thinkingCollapsed = prefs.thinkingCollapsed;
  }
  if (!pendingSettingKeys.has('calmMode') && typeof prefs.calmMode === 'boolean') {
    nextSettings.calmMode = prefs.calmMode;
  }
  if (!pendingSettingKeys.has('permissionPolicy') && prefs.permissionPolicy !== undefined) {
    const policy = sanitizePermissionPolicy(prefs.permissionPolicy);
    if (Object.keys(policy).length > 0) nextSettings.permissionPolicy = policy;
  }
  if (!pendingSettingKeys.has('defaultMode') && (prefs.defaultMode === 'build' || prefs.defaultMode === 'plan')) {
    nextSettings.defaultMode = prefs.defaultMode;
  }
  const next: UserProfile = {
    ...profileCache,
    provider: {
      activeProvider: String(payload.activeProviderId ?? '') || profileCache.provider.activeProvider,
      activeModel: String(payload.activeModelId ?? '') || profileCache.provider.activeModel,
    },
    providerSettings:
      (payload.providerSettings as Record<string, unknown> | undefined) ?? profileCache.providerSettings,
    settings: nextSettings,
  };
  profileCache = next;
  hydrated = true;
  // Notify each listener exactly once per payload; listeners registered
  // during dispatch run on the next hydration.
  for (const cb of hydrationListeners.splice(0)) cb(next);
}

async function hydrateFromServer(): Promise<void> {
  try {
    const resp = await fetch(appConfig.buildUrl('/profile'), {
      signal: AbortSignal.timeout(appConfig.timeout.fetchMs),
    });
    if (!resp.ok) throw new Error(`profile fetch failed: HTTP ${resp.status}`);
    applyServerPayload((await resp.json()) as Record<string, unknown>);
  } catch {
    // Backend not reachable yet — retry with a bounded schedule so a
    // late-starting backend still hydrates the profile eventually.
    if (hydrateAttempts >= HYDRATE_MAX_ATTEMPTS) return;
    hydrateAttempts += 1;
    if (hydrateTimer) clearTimeout(hydrateTimer);
    hydrateTimer = setTimeout(() => {
      void hydrateFromServer();
    }, HYDRATE_RETRY_MS);
  }
}

function scheduleRemoteSave(settingKeys: string[]): void {
  if (saveTimer) clearTimeout(saveTimer);
  saveTimer = setTimeout(() => {
    const { theme, thinkingCollapsed, calmMode, permissionPolicy, defaultMode } = profileCache.settings;
    void fetch(appConfig.buildUrl('/profile/preferences'), {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ theme, thinkingCollapsed, calmMode, permissionPolicy, defaultMode }),
    })
      .then((resp) => {
        if (resp.ok) {
          for (const key of settingKeys) pendingSettingKeys.delete(key);
        }
      })
      .catch(() => {
        // Keys stay pending: hydration must keep respecting local values.
      });
  }, 500);
}

/** Kick off hydration once the backend is expected to be reachable. */
export const initUserProfileSync = (): void => {
  void hydrateFromServer();
};

export const onProfileHydrated = (cb: (p: UserProfile) => void): void => {
  if (hydrated) cb(profileCache);
  else hydrationListeners.push(cb);
};

export const loadUserProfile = (): UserProfile => profileCache;

/** Deep-partial update shape: sections merge over the current profile. */
export interface UserProfileUpdates {
  provider?: Partial<UserProviderSection>;
  settings?: Partial<UserSettingsSection>;
  providerSettings?: Record<string, unknown>;
  lastActiveWorkspace?: string;
  sessionCount?: number;
  lastSessionTimestamp?: string;
}

export const saveUserProfile = (updates: UserProfileUpdates): UserProfile => {
  const settingKeys = updates.settings ? Object.keys(updates.settings) : [];
  const updatedProfile: UserProfile = {
    ...profileCache,
    ...updates,
    provider: updates.provider ? { ...profileCache.provider, ...updates.provider } : profileCache.provider,
    settings: updates.settings ? { ...profileCache.settings, ...updates.settings } : profileCache.settings,
    updatedAt: new Date().toISOString(),
  };

  for (const key of settingKeys) pendingSettingKeys.add(key);
  profileCache = updatedProfile;
  if (settingKeys.length > 0) scheduleRemoteSave(settingKeys);
  return updatedProfile;
};
