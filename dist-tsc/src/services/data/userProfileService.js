import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
let profileCache = null;
const PROFILE_DIR = path.join(os.homedir(), '.zenith');
const PROFILE_PATH = path.join(PROFILE_DIR, 'profile.json');
const DEFAULT_THEME = 'graphite';
const DEFAULT_MODE = 'build';
function getInitialProfile() {
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
function ensureDir() {
    try {
        if (!fs.existsSync(PROFILE_DIR)) {
            fs.mkdirSync(PROFILE_DIR, { recursive: true });
        }
    }
    catch {
        // Ignore mkdir errors (permissions, etc.)
    }
}
function readFromDisk() {
    try {
        ensureDir();
        if (fs.existsSync(PROFILE_PATH)) {
            const raw = fs.readFileSync(PROFILE_PATH, 'utf-8');
            const parsed = JSON.parse(raw);
            if (parsed && typeof parsed === 'object' && parsed.settings) {
                return parsed;
            }
        }
    }
    catch {
        // Ignore read errors
    }
    return null;
}
function writeToDisk(profile) {
    try {
        ensureDir();
        fs.writeFileSync(PROFILE_PATH, JSON.stringify(profile, null, 2), 'utf-8');
    }
    catch {
        // Ignore write errors
    }
}
let saveTimer = null;
function debouncedSave(profile) {
    if (saveTimer)
        clearTimeout(saveTimer);
    saveTimer = setTimeout(() => writeToDisk(profile), 500);
}
export const loadUserProfile = () => {
    if (profileCache)
        return profileCache;
    profileCache = readFromDisk() || getInitialProfile();
    return profileCache;
};
export const saveUserProfile = (updates) => {
    const current = loadUserProfile();
    const updatedProfile = {
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
