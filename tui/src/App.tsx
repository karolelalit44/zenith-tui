import { Box, Static, Text } from 'ink';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { BootLoading } from './components/BootLoading';
import { ScenarioRenderer } from './components/Display/Scenario';
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
import type { ScenarioEvent, ScenarioMode, TurnManifestEvent } from './types/scenario';
import type { AppStartupState } from './types/startup';
import { consolidateCompactionEvents } from './utils/compaction';
import { convertHistoryToTurns } from './utils/historyToTurns';
import { sanitizeSingleLine, truncateEnd } from './utils/text';
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
  /** Index of this turn in the full turns array (for divider logic). */
  turnIndex: number;
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

  // Composed-context occupancy for the footer gauge: prefer the in-flight
  // compaction totals, then the latest backend success snapshot. Never the
  // cumulative run usage (`runTokens`).
  const footerContextPercent = useMemo(() => {
    if (footerContext && typeof footerContext.used === 'number' && footerContext.total && footerContext.total > 0) {
      return Math.min(100, (footerContext.used / footerContext.total) * 100);
    }
    if (contextInfo && contextInfo.total > 0) {
      return Math.max(0, Math.min(100, contextInfo.percent * 100));
    }
    return undefined;
  }, [footerContext, contextInfo]);

  const footerWindowEstimated = useMemo(() => {
    if ((footerContext?.total ?? 0) > 0) return false;
    return contextInfo?.windowEstimated === true;
  }, [footerContext, contextInfo]);

  useEffect(() => {
    if (!isRunning) {
      setLiveRunTokens(runTokens);
      return;
    }
    const now = Date.now();
    if (now - lastTokenUpdateRef.current > 2000) {
      lastTokenUpdateRef.current = now;
      setLiveRunTokens(runTokens + estimateTokensForEvents(events));
    }
  }, [runTokens, isRunning, events]);

  useEffect(() => {
    // contentHeight tracks completed turns only; the live running block is
    // always rendered below the window and is NOT part of the scrollable
    // region. Counting streamed events here used to make the scroll offset
    // jump on every incoming event (the jitter during generation).
    const estimatedHeight = completedTurns.length * 15;
    updateContentHeight(estimatedHeight);
  }, [completedTurns.length, updateContentHeight]);

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
      setActiveSessionId(sessionId);
      const turns = convertHistoryToTurns(messages ?? [], selectedMode);
      if (turns.length > 0) {
        loadTurns(turns);
      } else {
        clearTurns();
      }
    },
    [setActiveSessionId, clearTurns, loadTurns, selectedMode],
  );

  const handleCancel = useCallback(() => {
    abort();
    abortActiveTurn(eventsRef.current);
    setRetryTarget(null);
  }, [abort, abortActiveTurn, eventsRef]);

  const handleNewChat = useCallback(() => {
    setActiveSessionId(null);
    clearTurns();
    setRetryTarget(null);
    setContinueTarget(null);
  }, [setActiveSessionId, clearTurns]);

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
      if (hadRecoverableError) {
        if (lastManifest) {
          setContinueTarget({
            prompt: activeTurn.prompt,
            manifest: lastManifest.manifest,
          });
        } else {
          setRetryTarget({
            prompt: activeTurn.prompt,
            mode: activeTurn.mode,
            model: activeTurn.model,
          });
        }
      }
      const finalTurnEvents = eventsRef.current.length >= events.length ? eventsRef.current : events;
      completeActiveTurn(finalTurnEvents);
      refreshStats();
    }
  }, [isRunning, events, eventsRef, activeTurn, completeActiveTurn, refreshStats, lastManifest]);

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
      items.push({ id: `msg_${turn.id}`, type: 'message', turn, turnIndex: i });
      if (turn.isComplete && turn.events.length > 0) {
        items.push({ id: `resp_${turn.id}`, type: 'response', turn, turnIndex: i });
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
                  {/* Divider between turns */}
                  {item.turnIndex > 0 ? (
                    <Box marginTop={1} marginBottom={0} width="100%">
                      <Text color={theme.colors.border.muted} wrap="truncate-end">
                        {'─'.repeat(Math.max(10, (termDims.columns || 80) - 2))}
                      </Text>
                    </Box>
                  ) : null}
                  <Box marginTop={1} flexDirection="column" width="100%">
                    <UserMessageBlock
                      prompt={item.turn.prompt}
                      model={item.turn.model}
                      timestamp={item.turn.timestamp}
                      timestampLong={item.turn.timestampLong}
                      attachments={item.turn.attachments}
                    />
                  </Box>
                </Box>
              );
            }

            // type === 'response'
            return (
              <Box key={item.id} flexDirection="column" width={contentWidth}>
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
            />
            {scrollState.isUserScrolled && (
              <Box paddingX={1} marginTop={0}>
                <Text color={theme.colors.text.dim} dimColor>
                  ▸ PgDn / End to follow live output
                </Text>
              </Box>
            )}
          </Box>
        )}

        {!showFilePicker && !isOverlayOpen && !showPalette && (
          <Box flexDirection="column" width="100%">
            {continueTarget && (
              <OptionBanner
                title="Continue where you left off"
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

            <CommandInput
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
              historyUp={historyUp}
              historyDown={historyDown}
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
