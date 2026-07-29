const STORAGE_KEY = 'zenith_recent_sessions';
const MAX_SESSIONS = 3;

interface SessionItem {
  time: string;
  title: string;
}

function loadSessions(): SessionItem[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      return JSON.parse(raw) as SessionItem[];
    }
  } catch {
    // corrupted storage, start fresh
  }
  return [];
}

function saveSessions(sessions: SessionItem[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions));
  } catch {
    // storage full or unavailable — silently ignore
  }
}

export const getRecentSessions = (): SessionItem[] => loadSessions();

export const addSession = (title: string): void => {
  const now = new Date();
  const day = now.getDate();
  const month = now.toLocaleString('default', { month: 'short' });
  const timeStr = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });

  const newSession: SessionItem = {
    time: `${timeStr}, ${day} ${month}`,
    title,
  };

  const existing = loadSessions();
  const updated = [newSession, ...existing.filter((s) => s.title !== title)].slice(0, MAX_SESSIONS);
  saveSessions(updated);
};
