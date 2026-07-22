export interface SessionItem {
  time: string;
  title: string;
  persona: string;
}

const INITIAL_SESSIONS: SessionItem[] = [
  { time: '[ 15:35, 22 July ]', title: 'Refactored authentication flow', persona: 'Architect' },
  { time: '[ 14:10, 22 July ]', title: 'Containerized app with Docker', persona: 'Debugger' },
  { time: '[ 11:20, 22 July ]', title: 'Built React Dashboard UI components', persona: 'Creative' },
];

let sessions: SessionItem[] = [...INITIAL_SESSIONS];

export const getRecentSessions = (): SessionItem[] => sessions;

export const addSession = (title: string, persona: string): void => {
  const now = new Date();
  const day = now.getDate();
  const month = now.toLocaleString('default', { month: 'short' });
  const timeStr = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });

  const newSession: SessionItem = {
    time: `[ ${timeStr}, ${day} ${month} ]`,
    title,
    persona: persona.charAt(0).toUpperCase() + persona.slice(1),
  };

  sessions = [newSession, ...sessions.slice(0, 4)];
};
