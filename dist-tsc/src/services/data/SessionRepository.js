const STORAGE_KEY = 'zenith_recent_sessions';
const MAX_SESSIONS = 3;
function loadSessions() {
    try {
        const raw = localStorage.getItem(STORAGE_KEY);
        if (raw) {
            return JSON.parse(raw);
        }
    }
    catch {
    }
    return [];
}
function saveSessions(sessions) {
    try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions));
    }
    catch {
    }
}
export const getRecentSessions = () => loadSessions();
export const addSession = (title) => {
    const now = new Date();
    const day = now.getDate();
    const month = now.toLocaleString('default', { month: 'short' });
    const timeStr = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });
    const newSession = {
        time: `${timeStr}, ${day} ${month}`,
        title,
    };
    const existing = loadSessions();
    const updated = [newSession, ...existing.filter((s) => s.title !== title)].slice(0, MAX_SESSIONS);
    saveSessions(updated);
};
