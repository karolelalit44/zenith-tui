import { Box, Static, Text } from 'ink';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { BootLoading } from './components/BootLoading';
import {
  PinnedOrchestrationCard,
  PinnedTodoCard,
  ScenarioRenderer,
  SuccessCard,
} from './components/Display/Scenario';
import { UserMessageBlock } from './components/Display/Scenario/UserMessageBlock';
import { ScrollIndicator } from './components/Display/ScrollIndicator';
import { AutocompleteDropdown } from './components/Input/AutocompleteDropdown';
import { CommandInput } from './components/Input/CommandInput';
import { CommandPalette } from './components/Input/CommandPalette';
import { FilePickerModal } from './components/Input/FilePicker/FilePickerModal';
import { OptionBanner } from './components/ui/OptionBanner';
import { AppProvider } from './context/AppContext';
import { useAutocomplete } from './hooks/useAutocomplete';
import { useConversation } from './hooks/useConversation';
import { useOverlayManager } from './hooks/useOverlayManager';
import { useProvider } from './hooks/useProvider';
import { useScenario } from './hooks/useScenario';
import { useScrollState } from './hooks/useScrollState';
import { useTerminalDimensions } from './hooks/useTerminalDimensions';
import { useTerminalKeyboard } from './hooks/useTerminalKeyboard';
import { OverlayRouter } from './routes/OverlayRouter';
import { ExitScreen } from './screens/Exit/ExitScreen';
import { SetupWizard } from './screens/SetupWizard';
import { WelcomeScreen } from './screens/Welcome';
import type { CommandRunContext } from './services/api/CommandRegistry';
import { dispatchCommand } from './services/api/CommandRegistry';
import { startupService } from './services/api/StartupService';
import type { TokenUsageStats } from './services/api/TokenUsageService';
import { tokenUsageService } from './services/api/TokenUsageService';
import { estimateTokensForEvents } from './services/api/tokenEstimationService';
import { initUserProfileSync, loadUserProfile, saveUserProfile } from './services/api/userProfileService';
import { savePlanToFile } from './services/export/markdownExport';
import { getActiveGitBranch } from './services/git';
import { providerRepository } from './services/providers/ProviderRepository';
import type { SessionSummary } from './services/transport/WebSocketClient';
import { wsClient } from './services/transport/WebSocketClient';
import { useTheme } from './theme/ThemeContext';
import type { ScenarioEvent, ScenarioMode, SuccessEvent, TokenInfo, TurnManifestEvent } from './types/scenario';
import type { AppStartupState } from './types/startup';
import { consolidateCompactionEvents } from './utils/compaction';
import { convertHistoryToTurns } from './utils/historyToTurns';
import { consolidateOrchestrationEvents } from './utils/orchestration';
import { sanitizeSingleLine, truncateEnd } from './utils/text';
import { consolidateTodoBoardEvents } from './utils/todoBoard';
import { formatTurnCost, resolveTurnUsage } from './utils/turnUsage';
import { resolveWorkspaceRoot } from './utils/workspacePath';

/**
 * A flat item for the <Static> list. Each conversation turn produces two entries:
 *   1. 'message' — the UserMessageBlock (committed immediately on submission, never re-rendered)
 *   2. 'response' — the ScenarioRenderer (committed once the turn completes)
 *
 * Ink's <Static> renders each item exactly once when it first appears in the
 * items array and commits it to the terminal scrollback buffer permanently.
 */
interface StaticItem {
  id: string;
  type: 'message' | 'response';
  turn: import('./hooks/useConversation').ConversationTurn;
}

export interface RetryTarget {
  prompt: string;
  mode: ScenarioMode;
  model?: string;
}

export const App: React.FC = () => {
  const { theme } = useTheme();
  const [startupState, setStartupState] = useState<AppStartupState>(() => startupService.state);
  const [workspace, setWorkspace] = useState(() => resolveWorkspaceRoot());
  useEffect(() => {
    setWorkspace(resolveWorkspaceRoot());
  }, []);
  const [thinkingCollapsed, setThinkingCollapsed] = useState(() => loadUserProfile().settings.thinkingCollapsed);
  const [calmMode, setCalmMode] = useState(() => loadUserProfile().settings.calmMode);
  const [exitPhase, setExitPhase] = useState<'idle' | 'exiting'>('idle');

  useEffect(() => {
    initUserProfileSync();
    startupService.initialize().then(setStartupState);
    const unsub = startupService.subscribe(setStartupState);
    return unsub;
  }, []);

  const toggleThinking = useCallback(() => setThinkingCollapsed((p) => !p), []);
  // /clam — persist the preference immediately so it survives restarts and
  // syncs to other sessions via user_profile.json.
  const toggleCalmMode = useCallback(() => {
    setCalmMode((prev) => {
      const next = !prev;
      saveUserProfile({ settings: { calmMode: next } });
      return next;
    });
  }, []);
  const [showPalette, setShowPalette] = useState(false);
  const [historyExpanded, setHistoryExpanded] = useState(false);

  const [retryTarget, setRetryTarget] = useState<RetryTarget | null>(null);
  const handleRetryDismiss = useCallback(() => setRetryTarget(null), []);

  const {
    turns,
    completedTurns,
    activeTurn,
    totalTokens,
    runTokens,
    runPrompt,
    runCompletion,
    runEstimated,
    contextInfo,
    staticKey,
    addTurn,
    completeActiveTurn,
    abortActiveTurn,
    clearTurns,
    loadTurns,
    remountStatic,
  } = useConversation();

  const termDims = useTerminalDimensions(remountStatic);
  const contentWidth = termDims.columns ? Math.max(30, termDims.columns - 2) : '100%';

  const { scrollState, scrollUp, scrollDown, scrollToTop, scrollToBottom, resetScroll, updateContentHeight } =
    useScrollState();

  const { selectedMode, overlay, isOverlayOpen, openOverlay, closeOverlay, closeAllOverlays, handleModeSelect } =
    useOverlayManager();

  useEffect(() => {
    if (startupState.phase !== 'ready') return;
    let cancelled = false;
    providerRepository.fetchProviderList().then((list) => {
      if (cancelled) return;
      if (list && list.connected.length === 0) {
        openOverlay('provider');
      }
    });
    return () => {
      cancelled = true;
    };
  }, [startupState.phase, openOverlay]);

  const {
    input,
    showAutocomplete,
    showFilePicker,
    pickerPath,
    pickerQuery,
    handleInputChange,
    handleAutocompleteSelect,
    clearInput,
    insertFilePath,
    closeFilePicker,
    closeAutocomplete,
    addHistory,
    historyUp,
    historyDown,
    attachments,
    removeAttachment,
    clearAttachments,
  } = useAutocomplete();

  const handleSetShowPalette = useCallback(
    (show: boolean) => {
      setShowPalette(show);
      if (show) {
        closeAutocomplete();
        closeFilePicker();
      }
    },
    [closeAutocomplete, closeFilePicker],
  );

  const {
    events,
    isRunning,
    startScenario,
    abort,
    startCompaction,
    resetEvents,
    eventsRef,
    lastSessionId,
    setActiveSessionId,
    lastManifest,
    continueFromManifest,
  } = useScenario();
  const { activeProvider } = useProvider();
  const activeGitBranch = useMemo(() => getActiveGitBranch(workspace), [workspace]);
  const [continueTarget, setContinueTarget] = useState<{ prompt: string; manifest: TurnManifestEvent } | null>(null);
  const [tokenUsageStats, setTokenUsageStats] = useState<TokenUsageStats | null>(null);

  const refreshStats = useCallback(() => {
    tokenUsageService.fetchStats().then(setTokenUsageStats);
  }, []);

  useEffect(() => {
    if (startupState.phase === 'ready') {
      refreshStats();
    }
  }, [startupState.phase, refreshStats]);

  // Throttle live token estimate: recalculate at most every 2 s while running
  // so that each streamed event does not trigger a full CommandInput re-render.
  const lastTokenUpdateRef = useRef(0);
  const [liveRunTokens, setLiveRunTokens] = useState(runTokens);

  // Derive the single consolidated compaction-flow state from the live event
  // stream so the footer token usage reflects the real, in-progress compaction.
  const compactionEvent = useMemo(() => consolidateCompactionEvents(events), [events]);

  // Prefer the model-reported context usage (compaction used/total) over the
  // frontend token estimate so the footer shows the latest session context.
  const footerContext = useMemo(() => {
    if (!compactionEvent) return null;
    const used = compactionEvent.afterTokens ?? compactionEvent.beforeTokens;
    return {
      used: typeof used === 'number' ? used : null,
      total: compactionEvent.totalTokens ?? null,
    };
  }, [compactionEvent]);

  // The latest backend success/usage snapshot from the LIVE stream. The moment
  // it arrives the TUI must surface its authoritative values (occupancy %,
  // window estimate, cumulative run total) instead of the stale committed-turn
  // snapshot or the frontend character estimate.
  const liveSuccessTokenInfo = useMemo(() => {
    let latest: TokenInfo | undefined;
    for (const e of events) {
      if (e.kind === 'success' && e.tokenInfo) latest = e.tokenInfo;
    }
    return latest;
  }, [events]);

  // Composed-context occupancy for the footer gauge: prefer the in-flight
  // compaction totals, then the latest backend success snapshot. Never the
  // cumulative run usage (`runTokens`).
  const footerContextPercent = useMemo(() => {
    if (footerContext && typeof footerContext.used === 'number' && footerContext.total && footerContext.total > 0) {
      return Math.min(100, (footerContext.used / footerContext.total) * 100);
    }
    if (liveSuccessTokenInfo && typeof liveSuccessTokenInfo.percent === 'number' && liveSuccessTokenInfo.total > 0) {
      return Math.max(0, Math.min(100, liveSuccessTokenInfo.percent * 100));
    }
    if (contextInfo && contextInfo.total > 0) {
      return Math.max(0, Math.min(100, contextInfo.percent * 100));
    }
    return undefined;
  }, [footerContext, contextInfo, liveSuccessTokenInfo]);

  const footerWindowEstimated = useMemo(() => {
    if ((footerContext?.total ?? 0) > 0) return false;
    if (liveSuccessTokenInfo?.windowEstimated === true) return true;
    return contextInfo?.windowEstimated === true;
  }, [footerContext, contextInfo, liveSuccessTokenInfo]);

  const turnUsageCosts = useMemo(() => {
    const map = new Map<string, string>();
    for (const t of completedTurns) {
      const cost = formatTurnCost(resolveTurnUsage(t.events));
      if (cost) map.set(t.id, cost);
    }
    return map;
  }, [completedTurns]);

  // Derive the active todo board from the live event stream, or fall back to
  // the latest turn's todo board if live stream has not emitted one yet.
  const activeTodoBoard = useMemo(() => {
    const liveBoard = consolidateTodoBoardEvents(events);
    if (liveBoard?.board && liveBoard.board.length > 0) return liveBoard;
    for (let i = turns.length - 1; i >= 0; i--) {
      const turnBoard = consolidateTodoBoardEvents(turns[i].events);
      if (turnBoard?.board && turnBoard.board.length > 0) return turnBoard;
    }
    return null;
  }, [events, turns]);

  // Derive the active orchestration from the live event stream, or fall back to
  // the latest turn's orchestration if live stream has not emitted one yet.
  // Only the most recent turn may recap: an older mission's card must not stay
  // pinned across unrelated turns.
  const activeOrchestration = useMemo(() => {
    const liveOrch = consolidateOrchestrationEvents(events);
    if (liveOrch && liveOrch.crewmates && liveOrch.crewmates.length > 0) return liveOrch;
    if (turns.length === 0) return null;
    const turnOrch = consolidateOrchestrationEvents(turns[turns.length - 1].events);
    return turnOrch && turnOrch.crewmates && turnOrch.crewmates.length > 0 ? turnOrch : null;
  }, [events, turns]);

  // The live status row event for the actively running turn. Rendered directly
  // above CommandInput (and below the pinned orchestration and todo panels)
  // so the execution hierarchy remains truthful:
  // chat stream -> captain panel -> todo panel -> duration & token status row -> composer.
  const liveSuccessEvent = useMemo<ScenarioEvent>(() => {
    const existing = events.find((e) => e.kind === 'success');
    if (existing) return existing;
    const estTokens = estimateTokensForEvents(events);
    const fallbackTokens = estTokens > 0 ? estTokens : events.length > 0 ? 1 : 0;
    return {
      kind: 'success',
      id: 'evt_live_status_row',
      elapsedMs: 0,
      tokenInfo:
        fallbackTokens > 0
          ? {
              used: fallbackTokens,
              total: 0,
              remaining: 0,
              percent: 0,
              estimated: true,
            }
          : undefined,
    } as ScenarioEvent;
  }, [events]);

  const liveSuccessContext = useMemo(
    () => ({
      isRunning: true,
      isHistorical: false,
    }),
    [],
  );

  // Derive the active sub-stage/activity for the running turn to surface in the pinned card
  const activeTaskActivity = useMemo(() => {
    if (!isRunning || events.length === 0) return undefined;
    for (let i = events.length - 1; i >= 0; i--) {
      const e = events[i];
      if (e.kind === 'message') {
        // Active turn is streaming conversational output; no background tool is executing
        return undefined;
      }
      if (e.kind === 'progress' && e.label) {
        return { label: e.label, percent: e.percent };
      }
      if (e.kind === 'tool_step' && e.tool) {
        if (e.pending) {
          const p = (e.params?.filepath || e.params?.path || e.params?.command || e.params?.query || '') as string;
          const out = p ? `${e.tool} (${p})` : e.tool;
          return { label: out, tool: e.tool };
        }
        // Tool has finished executing; stop search so completed tools do not show active spinners
        return undefined;
      }
      if (e.kind === 'tool_call' && e.tool) {
        const p = (e.params?.filepath || e.params?.path || e.params?.command || e.params?.query || '') as string;
        const out = p ? `${e.tool} (${p})` : e.tool;
        return { label: out, tool: e.tool };
      }
      if (e.kind === 'thinking') {
        return { label: 'Reasoning...', isThinking: true };
      }
    }
    return undefined;
  }, [isRunning, events]);

  useEffect(() => {
    if (!isRunning) {
      setLiveRunTokens(runTokens);
      return;
    }
    // The backend's cumulative run total is authoritative: the instant its
    // usage/success event arrives, surface THAT number, not the estimate.
    if (
      liveSuccessTokenInfo &&
      typeof liveSuccessTokenInfo.runTotal === 'number' &&
      liveSuccessTokenInfo.runTotal > 0
    ) {
      setLiveRunTokens(liveSuccessTokenInfo.runTotal);
      return;
    }
    const now = Date.now();
    if (now - lastTokenUpdateRef.current > 2000) {
      lastTokenUpdateRef.current = now;
      setLiveRunTokens(runTokens + estimateTokensForEvents(events));
    }
  }, [runTokens, isRunning, events, liveSuccessTokenInfo]);

  const activeMessageText = useMemo(() => {
    for (let i = events.length - 1; i >= 0; i--) {
      if (events[i].kind === 'message') {
        return (events[i] as import('./types/scenario').MessageEvent).text || '';
      }
    }
    return '';
  }, [events]);

  const liveContentHeight = useMemo(() => {
    if (!isRunning) return completedTurns.length * 15;
    const msgLines = activeMessageText ? activeMessageText.split('\n').length : 0;
    const nonMsgCount = events.filter((e) => e.kind !== 'message').length;
    return Math.max(msgLines, 1) + nonMsgCount * 3;
  }, [isRunning, completedTurns.length, activeMessageText, events]);

  const localScrollOffset = useMemo(() => {
    if (!scrollState.isUserScrolled) return undefined;
    const linesFromBottom = Math.max(
      0,
      scrollState.contentHeight - (scrollState.scrollOffset + scrollState.viewportHeight),
    );
    const msgLines = activeMessageText ? activeMessageText.split('\n').length : 0;
    const maxMsgOffset = Math.max(0, msgLines - scrollState.viewportHeight);
    return Math.max(0, maxMsgOffset - linesFromBottom);
  }, [
    scrollState.isUserScrolled,
    scrollState.contentHeight,
    scrollState.scrollOffset,
    scrollState.viewportHeight,
    activeMessageText,
  ]);

  useEffect(() => {
    if (!isRunning || scrollState.isUserScrolled) {
      updateContentHeight(liveContentHeight);
    } else {
      const timer = setTimeout(() => {
        updateContentHeight(liveContentHeight);
      }, 250);
      return () => clearTimeout(timer);
    }
  }, [liveContentHeight, updateContentHeight, isRunning, scrollState.isUserScrolled]);

  useEffect(() => {
    if (!isRunning && activeTurn?.isComplete) {
      resetScroll();
    }
  }, [isRunning, activeTurn?.isComplete, resetScroll]);

  const handleCompact = useCallback(() => {
    // Never start a compaction underneath a streaming turn: the backend
    // serializes against the live context and a concurrent request would
    // silently interleave with it.
    if (isRunning) {
      addTurn('/compact', selectedMode);
      completeActiveTurn([
        {
          kind: 'warning',
          id: `evt_compact_busy_${Date.now()}`,
          message: 'Cannot compact while a turn is running — wait for it to finish or press ESC.',
        } as ScenarioEvent,
      ]);
      return;
    }
    addTurn('/compact', selectedMode);
    startCompaction();
  }, [addTurn, selectedMode, startCompaction, isRunning, completeActiveTurn]);

  const handleClearTools = useCallback(() => {
    if (!lastSessionId) return;
    wsClient
      .contextClearTools(lastSessionId)
      .then((res) => {
        if (res.removed > 0) {
          addTurn('/clear-tools', selectedMode);
          completeActiveTurn([
            {
              kind: 'message',
              id: `evt_cleartools_${Date.now()}`,
              text: `Cleared tool output from ${res.removed} message(s)`,
              partial: false,
            } as ScenarioEvent,
          ]);
        }
      })
      .catch(() => {});
  }, [lastSessionId, addTurn, completeActiveTurn, selectedMode]);

  const handleSavePlan = useCallback(() => {
    const targetTurn = turns[turns.length - 1];
    const targetEvents = isRunning ? events : targetTurn?.events || [];
    if (targetEvents.length > 0) {
      savePlanToFile(targetEvents, targetTurn?.prompt || 'Plan Request', workspace, 'implementation-plan.md');
    }
  }, [turns, events, isRunning, workspace]);

  const handleExit = useCallback(() => {
    setExitPhase('exiting');
  }, []);

  const handleSessionResume = useCallback(
    (sessionId: string, _summary: SessionSummary, messages?: Record<string, unknown>[]) => {
      // Stop any in-flight turn first: without abort, stale WS events from the
      // previous session repopulate the array right after resetEvents clears it.
      abort();
      setActiveSessionId(sessionId);
      resetEvents();
      const turns = convertHistoryToTurns(messages ?? [], selectedMode);
      if (turns.length > 0) {
        loadTurns(turns);
      } else {
        clearTurns();
      }
    },
    [abort, setActiveSessionId, resetEvents, clearTurns, loadTurns, selectedMode],
  );

  const handleCancel = useCallback(() => {
    abort();
    abortActiveTurn(eventsRef.current);
    setRetryTarget(null);
  }, [abort, abortActiveTurn, eventsRef]);

  const handleNewChat = useCallback(() => {
    abort();
    abortActiveTurn(eventsRef.current);
    setActiveSessionId(null);
    clearTurns();
    resetEvents();
    resetScroll();
    setRetryTarget(null);
    setContinueTarget(null);
  }, [abort, abortActiveTurn, eventsRef, setActiveSessionId, clearTurns, resetEvents, resetScroll]);

  const commandCtx = useMemo<CommandRunContext>(
    () => ({
      openOverlay,
      clearTurns: handleNewChat,
      clearTools: handleClearTools,
      setMode: handleModeSelect,
      openPalette: () => handleSetShowPalette(true),
      toggleThinking,
      toggleCalmMode,
      savePlan: handleSavePlan,
      triggerExit: handleExit,
      compactTurns: handleCompact,
    }),
    [
      openOverlay,
      handleNewChat,
      handleClearTools,
      handleModeSelect,
      handleSetShowPalette,
      toggleThinking,
      toggleCalmMode,
      handleSavePlan,
      handleExit,
      handleCompact,
    ],
  );

  const handleSubmit = useCallback(
    (value: string) => {
      const trimmed = value.trim();
      if (!trimmed) return;
      if (trimmed.startsWith('/')) {
        clearInput();
        dispatchCommand(trimmed, commandCtx);
        return;
      }

      // A prompt while a turn is streaming would overwrite the active runner
      // without aborting it (lost stream, orphaned backend task). Commands
      // (incl. /cancel) were already dispatched above; plain prompts wait.
      if (isRunning) return;
      const providerId = activeProvider.id;
      const modelId = activeProvider.config.model || activeProvider.meta.defaultModel || undefined;

      addHistory(trimmed);
      addTurn(trimmed, selectedMode, modelId, attachments);
      clearInput();
      clearAttachments();
      setRetryTarget(null);
      setHistoryExpanded(false);
      startScenario(trimmed, selectedMode, providerId, modelId, attachments);
    },
    [
      selectedMode,
      startScenario,
      activeProvider.id,
      activeProvider.config.model,
      activeProvider.meta.defaultModel,
      addTurn,
      clearInput,
      clearAttachments,
      commandCtx,
      addHistory,
      attachments,
      isRunning,
    ],
  );

  useTerminalKeyboard({
    turns,
    isRunning,
    events,
    eventsRef,
    overlay,
    openOverlay,
    closeOverlay,
    closeAllOverlays,
    abort,
    abortActiveTurn,
    clearTurns: handleNewChat,
    onToggleThinking: toggleThinking,
    scrollUp,
    scrollDown,
    scrollToTop,
    scrollToBottom,
    showPalette,
    setShowPalette: handleSetShowPalette,
    slashMenuOpen: showAutocomplete,
    onToggleHistoryExpanded: () => setHistoryExpanded((v) => !v),
  });

  useEffect(() => {
    if (!isRunning && events.length > 0 && activeTurn && !activeTurn.isComplete) {
      const hadRecoverableError = eventsRef.current.some((e) => e.kind === 'error' && e.recoverable);
      const successEvt = eventsRef.current.find((e) => e.kind === 'success') as SuccessEvent | undefined;
      const manifestEvt =
        lastManifest?.manifest ||
        (eventsRef.current.find((e) => e.kind === 'turn_manifest') as TurnManifestEvent | undefined) ||
        successEvt?.manifest;
      const isTruncated =
        successEvt?.truncated === true ||
        successEvt?.finishReason === 'length' ||
        Boolean(manifestEvt?.remaining?.some((r) => r.toLowerCase().includes('token limit')));
      const hasPendingViaManifest = (manifestEvt?.remaining?.length ?? 0) > 0;
      const isStalled = manifestEvt?.stalled === true;
      const isNonTruncatedIncomplete =
        !isTruncated &&
        !isStalled &&
        hasPendingViaManifest &&
        ((successEvt && successEvt.completed === false) || (manifestEvt && manifestEvt.completed === false));
      const isIncomplete = isTruncated || isNonTruncatedIncomplete;

      if (hadRecoverableError) {
        if (manifestEvt) {
          setContinueTarget({
            prompt: activeTurn.prompt,
            manifest: manifestEvt,
          });
        } else {
          setRetryTarget({
            prompt: activeTurn.prompt,
            mode: activeTurn.mode,
            model: activeTurn.model,
          });
        }
      } else if (isIncomplete) {
        const effectiveManifest: TurnManifestEvent = manifestEvt || {
          kind: 'turn_manifest',
          id: `manifest_${Date.now()}`,
          created: [],
          modified: [],
          remaining: isTruncated ? ['Response truncated by token limit.'] : [],
          completed: false,
          stalled: false,
          files: [],
        };
        const continuePrompt = isTruncated
          ? 'Your response was cut off by the token limit. Please continue directly from where you left off without repeating any prior text.'
          : activeTurn.prompt;
        setContinueTarget({
          prompt: continuePrompt,
          manifest: effectiveManifest,
        });
      }
      const finalTurnEvents = eventsRef.current.length >= events.length ? eventsRef.current : events;
      completeActiveTurn(finalTurnEvents);
      refreshStats();
      scrollToBottom();
    }
  }, [isRunning, events, eventsRef, activeTurn, completeActiveTurn, refreshStats, lastManifest, scrollToBottom]);

  const handleAutocompleteSelectWithRouter = useCallback(
    (cmd: string) => {
      if (cmd.startsWith('/')) {
        clearInput();
        dispatchCommand(cmd, commandCtx);
      } else {
        handleAutocompleteSelect(cmd);
      }
    },
    [clearInput, commandCtx, handleAutocompleteSelect],
  );

  const handleRetry = useCallback(() => {
    if (!retryTarget || isRunning) return;
    const { prompt, mode, model } = retryTarget;
    addTurn(prompt, mode, model);
    clearInput();
    setRetryTarget(null);
    startScenario(prompt, mode, activeProvider.id, model);
  }, [retryTarget, isRunning, activeProvider.id, addTurn, clearInput, startScenario]);

  const handleContinue = useCallback(() => {
    if (!continueTarget || isRunning) return;
    const { prompt, manifest } = continueTarget;
    addTurn(prompt, selectedMode, activeProvider.config.model);
    clearInput();
    setContinueTarget(null);
    continueFromManifest(prompt, selectedMode, manifest, activeProvider.id, activeProvider.config.model);
  }, [
    continueTarget,
    isRunning,
    selectedMode,
    activeProvider.id,
    activeProvider.config.model,
    addTurn,
    clearInput,
    continueFromManifest,
  ]);

  const handleContinueDismiss = useCallback(() => setContinueTarget(null), []);

  const handleOpenHelp = useCallback(() => openOverlay('help'), [openOverlay]);

  const handleOpenProvider = useCallback(() => {
    closeOverlay();
    openOverlay('provider');
  }, [closeOverlay, openOverlay]);

  const handleToggleMode = useCallback(
    () => handleModeSelect(selectedMode === 'plan' ? 'build' : 'plan'),
    [handleModeSelect, selectedMode],
  );

  const handleSetupComplete = useCallback(() => {
    setStartupState({ phase: 'ready', result: startupState.result, error: null });
  }, [startupState]);

  /**
   * Build the flat static items list from all turns.
   *
   * Every turn immediately produces a 'message' item (committed to scrollback
   * on the first render after addTurn — never re-rendered). Completed turns
   * also produce a 'response' item (committed once completeActiveTurn runs).
   */
  const staticItems: StaticItem[] = useMemo(() => {
    const items: StaticItem[] = [];
    for (let i = 0; i < turns.length; i++) {
      const turn = turns[i];
      items.push({ id: `msg_${turn.id}`, type: 'message', turn });
      if (turn.isComplete && turn.events.length > 0) {
        items.push({ id: `resp_${turn.id}`, type: 'response', turn });
      }
    }
    return items;
  }, [turns]);

  const showScrollIndicator = scrollState.isUserScrolled && (isRunning || completedTurns.length > 0);

  if (startupState.phase === 'loading') {
    return <BootLoading />;
  }

  if (startupState.phase === 'setup' || startupState.phase === 'error') {
    return (
      <Box flexDirection="column" paddingX={1} paddingTop={1} width="100%">
        <SetupWizard startupState={startupState} onComplete={handleSetupComplete} />
      </Box>
    );
  }

  if (exitPhase === 'exiting') {
    return <ExitScreen />;
  }

  return (
    <AppProvider
      turns={turns}
      activeTurn={activeTurn}
      totalTokens={totalTokens}
      events={events}
      isRunning={isRunning}
      overlay={overlay}
      isOverlayOpen={isOverlayOpen}
      selectedMode={selectedMode}
      thinkingCollapsed={thinkingCollapsed}
    >
      <Box flexDirection="column" paddingX={1} paddingTop={1} width="100%">
        {turns.length === 0 && !isRunning && <WelcomeScreen workspace={workspace} />}

        {scrollState.isUserScrolled && turns.length > 3 && (
          <Box paddingX={1} marginBottom={1}>
            <Text color={theme.colors.text.muted} dimColor>
              ... earlier turns hidden (scroll up to view)
            </Text>
          </Box>
        )}

        {/* ── Static items: committed once to scrollback, never re-rendered ── */}
        <Static key={staticKey} items={staticItems}>
          {(item) => {
            if (item.type === 'message') {
              return (
                <Box key={item.id} flexDirection="column" width="100%">
                  <UserMessageBlock
                    prompt={item.turn.prompt}
                    model={item.turn.model}
                    timestamp={item.turn.timestamp}
                    timestampLong={item.turn.timestampLong}
                    attachments={item.turn.attachments}
                  />
                </Box>
              );
            }

            // type === 'response'
            const turnCost =
              (item.turn.events && item.turn.events.length > 0
                ? formatTurnCost(resolveTurnUsage(item.turn.events))
                : undefined) || turnUsageCosts.get(item.turn.id);
            return (
              <Box key={item.id} flexDirection="column" width={contentWidth}>
                {turnCost ? (
                  <Box marginBottom={1}>
                    <Text color={theme.colors.text.muted}>◈ {turnCost}</Text>
                  </Box>
                ) : null}
                <ScenarioRenderer
                  events={item.turn.events}
                  isRunning={false}
                  isHistorical={true}
                  thinkingCollapsed={thinkingCollapsed}
                  calmMode={calmMode}
                  workspaceName={workspace}
                  gitBranch={activeGitBranch}
                />
              </Box>
            );
          }}
        </Static>

        {/* ── Dynamic area: only the live streaming response ─────────── */}
        {/* No UserMessageBlock here — it's already committed to Static.  */}
        {(isRunning || (activeTurn && !activeTurn.isComplete)) && (
          <Box flexDirection="column" width={contentWidth}>
            <ScenarioRenderer
              events={events}
              isRunning={isRunning}
              isHistorical={false}
              thinkingCollapsed={thinkingCollapsed}
              calmMode={calmMode}
              historyExpanded={historyExpanded}
              workspaceName={workspace}
              gitBranch={activeGitBranch}
              scrollOffset={localScrollOffset}
              maxDynamicLines={scrollState.viewportHeight}
              showStatusRow={false}
            />
            {scrollState.isUserScrolled && (
              <Box paddingX={1} marginTop={0}>
                <Text color={theme.colors.text.dim} dimColor>
                  ▸ PgDn / End to follow live output (
                  {Math.max(0, scrollState.contentHeight - (scrollState.scrollOffset + scrollState.viewportHeight))}{' '}
                  lines below)
                </Text>
              </Box>
            )}
          </Box>
        )}

        {!showFilePicker && !isOverlayOpen && !showPalette && (
          <Box flexDirection="column" width="100%">
            {continueTarget && (
              <OptionBanner
                title={
                  continueTarget.manifest.remaining?.some((r) => r.toLowerCase().includes('token limit'))
                    ? 'Output truncated by token limit'
                    : 'Continue where you left off'
                }
                message={`Resume: ${truncateEnd(sanitizeSingleLine(continueTarget.prompt), 90)}`}
                options={[
                  { label: 'Continue', value: 'continue' },
                  { label: 'Dismiss', value: 'dismiss' },
                ]}
                onSelect={(value) => (value === 'continue' ? handleContinue() : handleContinueDismiss())}
                onClose={handleContinueDismiss}
              />
            )}
            {retryTarget && (
              <OptionBanner
                title="Task failed"
                message={`Retry: ${truncateEnd(sanitizeSingleLine(retryTarget.prompt), 90)}`}
                options={[
                  { label: 'Retry', value: 'retry' },
                  { label: 'Dismiss', value: 'dismiss' },
                ]}
                onSelect={(value) => (value === 'retry' ? handleRetry() : handleRetryDismiss())}
                onClose={handleRetryDismiss}
              />
            )}

            {activeOrchestration && (
              <Box marginBottom={1} width="100%">
                <PinnedOrchestrationCard
                  event={activeOrchestration}
                  isRunning={isRunning}
                />
              </Box>
            )}

            {activeTodoBoard && (
              <Box marginBottom={1} width="100%">
                <PinnedTodoCard
                  event={activeTodoBoard}
                  isRunning={isRunning}
                  activeActivity={activeTaskActivity}
                />
              </Box>
            )}

            {(isRunning || (activeTurn && !activeTurn.isComplete)) && (
              <Box width="100%">
                <SuccessCard
                  event={liveSuccessEvent as SuccessEvent}
                  context={liveSuccessContext}
                  manifest={lastManifest?.manifest}
                  turnEvents={events}
                />
              </Box>
            )}

            <CommandInput
              calmMode={calmMode}
              input={input}
              onInputChange={handleInputChange}
              onSubmit={handleSubmit}
              running={isRunning}
              disabled={!!retryTarget || !!continueTarget}
              disabledMessage={
                retryTarget ? 'Choose an action above…' : continueTarget ? 'Choose an action above…' : undefined
              }
              attachments={attachments}
              onRemoveAttachment={removeAttachment}
              onClearAttachments={clearAttachments}
              historyUp={historyUp}
              historyDown={historyDown}
              scrollUp={scrollUp}
              scrollDown={scrollDown}
              mode={selectedMode}
              maxTokens={footerContext?.total ?? (providerRepository.maxContextTokens || undefined)}
              runTokens={liveRunTokens}
              runEstimated={runEstimated}
              contextPercent={footerContextPercent}
              windowEstimated={footerWindowEstimated}
              workspaceName={workspace}
              onCancel={handleCancel}
              onOpenHelp={handleOpenHelp}
              onOpenMode={handleToggleMode}
              onClearInput={clearInput}
              slashMenuOpen={showAutocomplete}
            />
          </Box>
        )}

        {showPalette && (
          <Box marginTop={1} width="100%">
            <CommandPalette ctx={commandCtx} onClose={() => handleSetShowPalette(false)} />
          </Box>
        )}

        {showAutocomplete && (
          <Box marginTop={1} width="100%">
            <AutocompleteDropdown
              input={input}
              onSelect={handleAutocompleteSelectWithRouter}
              onClose={closeAutocomplete}
              onQueryChange={handleInputChange}
            />
          </Box>
        )}

        {showFilePicker && (
          <Box marginTop={1} width="100%">
            <FilePickerModal
              onSelectFile={insertFilePath}
              onClose={closeFilePicker}
              initialPath={pickerPath}
              initialQuery={pickerQuery}
            />
          </Box>
        )}

        {showScrollIndicator && (
          <ScrollIndicator
            visible={true}
            scrollOffset={scrollState.scrollOffset}
            totalLines={scrollState.contentHeight}
          />
        )}

        <OverlayRouter
          overlay={overlay}
          isOverlayOpen={isOverlayOpen}
          selectedMode={selectedMode}
          totalTokens={totalTokens}
          events={events}
          runTokens={runTokens}
          runPrompt={runPrompt}
          runCompletion={runCompletion}
          runEstimated={runEstimated}
          contextInfo={contextInfo}
          tokenUsageStats={tokenUsageStats}
          onSelectMode={handleModeSelect}
          onClose={closeOverlay}
          onComplete={handleSetupComplete}
          onOpenProvider={handleOpenProvider}
          onResumeSession={handleSessionResume}
          onCompactNow={handleCompact}
        />
      </Box>
    </AppProvider>
  );
};
