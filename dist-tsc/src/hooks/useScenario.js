import { useCallback, useEffect, useRef, useState } from 'react';
import { backendScenarioProvider } from '../services/backend/BackendScenarioProvider';
import { wsClient } from '../services/backend/WebSocketClient';
import { eventBus } from '../services/eventBus';
export function useScenario() {
    const [events, setEvents] = useState([]);
    const eventsRef = useRef([]);
    const [isRunning, setIsRunning] = useState(false);
    const [activeConfirmation, setActiveConfirmation] = useState(null);
    const [lastSessionId, setLastSessionId] = useState(null);
    const runnerRef = useRef(null);
    const sessionIdRef = useRef(null);
    useEffect(() => {
        wsClient.connect().catch(() => { });
    }, []);
    const handleEvent = useCallback((event, index) => {
        setEvents((prev) => {
            let next;
            if (typeof index === 'number' && index < prev.length) {
                next = [...prev];
                next[index] = event;
            }
            else {
                next = [...prev, event];
            }
            eventsRef.current = next;
            return next;
        });
        if (event.kind === 'confirmation_request') {
            const conf = event;
            setActiveConfirmation(conf.answered ? null : conf);
        }
    }, []);
    const handleComplete = useCallback(() => {
        setIsRunning(false);
        setActiveConfirmation(null);
    }, []);
    const connectToBackend = useCallback(async () => {
        await wsClient.connect();
    }, []);
    const reportError = useCallback((id, message) => {
        setEvents((prev) => {
            const next = [...prev, { kind: 'error', id: `evt_${id}_${Date.now()}`, message }];
            eventsRef.current = next;
            return next;
        });
        setIsRunning(false);
    }, []);
    const startScenario = useCallback(async (prompt, selectedMode, provider) => {
        setEvents([]);
        eventsRef.current = [];
        setIsRunning(true);
        try {
            await connectToBackend();
        }
        catch {
            reportError('conn', 'Cannot connect to backend. Run: zenith serve');
            return;
        }
        try {
            if (sessionIdRef.current) {
                try {
                    const result = await wsClient.resumeSession(sessionIdRef.current);
                    const resumed = result.session;
                    if (resumed?.id && resumed.id !== sessionIdRef.current) {
                        sessionIdRef.current = resumed.id;
                    }
                }
                catch {
                    sessionIdRef.current = null;
                }
            }
            if (!sessionIdRef.current) {
                const session = await wsClient.createSession(prompt.slice(0, 50));
                sessionIdRef.current = session.id;
                setLastSessionId(session.id);
            }
        }
        catch {
            reportError('sess', 'Failed to create session');
            return;
        }
        const scenario = {
            ...backendScenarioProvider.resolve(prompt, selectedMode),
            sessionId: sessionIdRef.current ?? undefined,
        };
        runnerRef.current = backendScenarioProvider.execute(scenario, handleEvent, handleComplete);
        wsClient.sendPrompt(prompt, selectedMode, sessionIdRef.current ?? undefined, provider).catch((err) => {
            const message = err instanceof Error ? err.message : String(err);
            reportError('prompt_err', `Backend prompt error: ${message}`);
        });
    }, [connectToBackend, handleEvent, handleComplete, reportError]);
    const abort = useCallback(() => {
        runnerRef.current?.abort();
        setIsRunning(false);
        setActiveConfirmation(null);
    }, []);
    const respondConfirmation = useCallback(async (approved) => {
        const conf = activeConfirmation;
        if (!conf?.confirmationId)
            return;
        wsClient.sendConfirmation(conf.confirmationId, approved).catch(() => { });
        eventBus.emit('confirmation:response', { confirmationId: conf.confirmationId, approved });
        setEvents((prev) => prev.map((e) => e.kind === 'confirmation_request' && e.confirmationId === conf.confirmationId
            ? { ...e, answered: true, approved }
            : e));
        setActiveConfirmation(null);
    }, [activeConfirmation]);
    return {
        events,
        eventsRef,
        isRunning,
        startScenario,
        abort,
        activeConfirmation,
        respondConfirmation,
        lastSessionId,
    };
}
