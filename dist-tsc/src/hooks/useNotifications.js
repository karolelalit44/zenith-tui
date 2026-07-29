import { useCallback, useRef, useState } from 'react';
import { NOTIFICATION_DURATION_MS } from '../constants/layout';
export function useNotifications() {
    const [notifications, setNotifications] = useState([]);
    const timersRef = useRef(new Map());
    const removeNotification = useCallback((id) => {
        const timer = timersRef.current.get(id);
        if (timer) {
            clearTimeout(timer);
            timersRef.current.delete(id);
        }
        setNotifications((prev) => prev.filter((n) => n.id !== id));
    }, []);
    const addNotification = useCallback((message, type = 'info', duration = NOTIFICATION_DURATION_MS) => {
        const id = `notif_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`;
        const notification = { id, message, type, timestamp: Date.now() };
        setNotifications((prev) => [...prev, notification]);
        if (duration > 0) {
            const timer = setTimeout(() => removeNotification(id), duration);
            timersRef.current.set(id, timer);
        }
    }, [removeNotification]);
    const clearNotifications = useCallback(() => {
        timersRef.current.forEach((timer) => clearTimeout(timer));
        timersRef.current.clear();
        setNotifications([]);
    }, []);
    return { notifications, addNotification, removeNotification, clearNotifications };
}
