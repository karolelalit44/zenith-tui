import { wsClient } from './WebSocketClient';

export interface BackendSession {
  id: string;
  title: string;
  mode: string;
  created_at: string;
  updated_at: string;
  is_active: boolean;
}

export interface SessionItem {
  time: string;
  title: string;
  id: string;
}

export class SessionService {
  async create(title?: string): Promise<BackendSession> {
    const result = await wsClient.createSession(title);
    return result as unknown as BackendSession;
  }

  async list(): Promise<SessionItem[]> {
    const sessions = await wsClient.listSessions();
    return (sessions as BackendSession[]).map((s) => ({
      id: s.id,
      title: s.title,
      time: formatTimestamp(s.created_at),
    }));
  }

  async resume(sessionId: string): Promise<{ session: BackendSession; messages: unknown[] }> {
    return wsClient.resumeSession(sessionId) as unknown as Promise<{ session: BackendSession; messages: unknown[] }>;
  }
}

function formatTimestamp(iso: string): string {
  try {
    const d = new Date(iso);
    const time = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });
    const day = d.getDate();
    const month = d.toLocaleString('default', { month: 'short' });
    return `${time}, ${day} ${month}`;
  } catch {
    return iso;
  }
}

export const sessionService = new SessionService();
