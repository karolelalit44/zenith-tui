import { wsClient } from '../backend/WebSocketClient';
export const getRecentSessions = async (limit = 10) => {
    try {
        const summaries = await wsClient.listSessionSummaries({ limit, include_archived: false });
        return summaries.map((s) => ({
            id: s.id,
            title: s.title || 'Untitled',
            time: s.created_at || s.updated_at || '',
            state: s.state || '',
            message_count: s.message_count || 0,
            total_tokens: s.total_tokens || 0,
        }));
    }
    catch {
        return [];
    }
};
export const addSession = async (title) => {
    try {
        await wsClient.createSession(title);
    }
    catch {
        // Silently handle — session is tracked server-side
    }
};
