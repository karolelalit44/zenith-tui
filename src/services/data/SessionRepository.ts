export interface SessionItem {
  time: string;
  title: string;
}

const INITIAL_SESSIONS: SessionItem[] = [{ time: '15:35, 22 July', title: 'Refactored authentication flow' }];

let sessions: SessionItem[] = [...INITIAL_SESSIONS];

export const getRecentSessions = (): SessionItem[] => sessions;

export const addSession = (title: string): void => {
  const now = new Date();
  const day = now.getDate();
  const month = now.toLocaleString('default', { month: 'short' });
  const timeStr = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });

  const newSession: SessionItem = {
    time: `${timeStr}, ${day} ${month}`,
    title,
  };

  sessions = [newSession, ...sessions.filter((s) => s.title !== title)].slice(0, 3);
};
