import { useCallback, useRef, useState } from 'react';
import { NOTIFICATION_DURATION_MS } from '../constants/layout';

export type NotificationType = 'success' | 'error' | 'info' | 'warning';

export interface Notification {
  id: string;
  message: string;
  type: NotificationType;
  timestamp: number;
}

export interface UseNotificationsReturn {
  notifications: Notification[];
  addNotification: (message: string, type?: NotificationType, duration?: number) => void;
  removeNotification: (id: string) => void;
  clearNotifications: () => void;
}

export function useNotifications(): UseNotificationsReturn {
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const timersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

  const removeNotification = useCallback((id: string) => {
    const timer = timersRef.current.get(id);
    if (timer) {
      clearTimeout(timer);
      timersRef.current.delete(id);
    }
    setNotifications((prev) => prev.filter((n) => n.id !== id));
  }, []);

  const addNotification = useCallback(
    (message: string, type: NotificationType = 'info', duration: number = NOTIFICATION_DURATION_MS) => {
      const id = `notif_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`;
      const notification: Notification = { id, message, type, timestamp: Date.now() };
      setNotifications((prev) => [...prev, notification]);

      if (duration > 0) {
        const timer = setTimeout(() => removeNotification(id), duration);
        timersRef.current.set(id, timer);
      }
    },
    [removeNotification],
  );

  const clearNotifications = useCallback(() => {
    timersRef.current.forEach((timer) => clearTimeout(timer));
    timersRef.current.clear();
    setNotifications([]);
  }, []);

  return { notifications, addNotification, removeNotification, clearNotifications };
}
