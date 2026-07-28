const INITIAL_SESSIONS = [];
let sessions = [...INITIAL_SESSIONS];
export const getRecentSessions = () => sessions;
export const addSession = (title) => {
    const now = new Date();
    const day = now.getDate();
    const month = now.toLocaleString('default', { month: 'short' });
    const timeStr = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });
    const newSession = {
        time: `${timeStr}, ${day} ${month}`,
        title,
    };
    sessions = [newSession, ...sessions.filter((s) => s.title !== title)].slice(0, 3);
};
