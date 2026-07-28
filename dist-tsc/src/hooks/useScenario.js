import { useCallback, useEffect, useRef, useState } from 'react';
import { backendScenarioProvider } from '../services/backend/BackendScenarioProvider';
import { wsClient } from '../services/backend/WebSocketClient';
import { eventBus } from '../services/eventBus';
export function useScenario() {
    const [events, setEvents] = useState([]);
    const [isRunning, setIsRunning] = useState(false);
    const [activeConfirmation, setActiveConfirmation] = useState(null);
    const [lastSessionId, setLastSessionId] = useState(null);
    const runnerRef = useRef(null);
    const sessionIdRef = useRef(null);
    useEffect(() => {
        wsClient.connect().catch(() => { });
    }, []);
    const handleEvent = useCallback((event, index) => {
        console.log(`[SCENARIO EVENT] kind=${event.kind} id=${event.id} index=${index}`);
        setEvents((prev) => {
            if (typeof index === 'number' && index < prev.length) {
                console.log(`[SCENARIO UPDATE] replacing event at index ${index} (prev_kind=${prev[index]?.kind})`);
                const updated = [...prev];
                updated[index] = event;
                return updated;
            }
            console.log(`[SCENARIO APPEND] adding new event (total=${prev.length + 1})`);
            return [...prev, event];
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
    const createSession = useCallback(async (prompt) => {
        const session = await wsClient.createSession(prompt.slice(0, 50));
        const id = session.id;
        sessionIdRef.current = id;
        setLastSessionId(id);
        return id;
    }, []);
    const connectToBackend = useCallback(async () => {
        await wsClient.connect();
    }, []);
    const reportError = useCallback((id, message) => {
        setEvents([{ kind: 'error', id: `evt_${id}_${Date.now()}`, message }]);
        setIsRunning(false);
    }, []);
    const startScenario = useCallback(async (prompt, selectedMode, provider) => {
        setEvents([]);
        setIsRunning(true);
        try {
            await connectToBackend();
        }
        catch {
            reportError('conn', 'Cannot connect to backend. Run: zenith serve');
            return;
        }
        try {
            if (!sessionIdRef.current)
                await createSession(prompt);
        }
        catch {
            reportError('sess', 'Failed to create session');
            return;
        }
        const scenario = backendScenarioProvider.resolve(prompt, selectedMode);
        runnerRef.current = backendScenarioProvider.execute(scenario, handleEvent, handleComplete);
        wsClient.sendPrompt(prompt, selectedMode, sessionIdRef.current ?? undefined, provider).catch((err) => {
            const message = err instanceof Error ? err.message : String(err);
            reportError('prompt_err', `Backend prompt error: ${message}`);
        });
    }, [connectToBackend, createSession, handleEvent, handleComplete, reportError]);
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
        isRunning,
        startScenario,
        abort,
        activeConfirmation,
        respondConfirmation,
        lastSessionId,
    };
}
