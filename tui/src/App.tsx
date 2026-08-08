import { Box, Static, Text } from 'ink';
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ScenarioRenderer } from './components/Display/Scenario';
import { UserMessageBlock } from './components/Display/Scenario/UserMessageBlock';
import { ScrollIndicator } from './components/Display/ScrollIndicator';
import { SessionStatusBar } from './components/Display/SessionStatusBar';
import { AutocompleteDropdown } from './components/Input/AutocompleteDropdown';
import { CommandInput } from './components/Input/CommandInput';
import { CommandPalette } from './components/Input/CommandPalette';
import { FilePickerModal } from './components/Input/FilePicker/FilePickerModal';
import { OptionBanner } from './components/ui/OptionBanner';
import { ASCII_SPINNER_FRAMES } from './constants/animation';
import { AppProvider } from './context/AppContext';
import { useAutocomplete } from './hooks/useAutocomplete';
import { useConversation } from './hooks/useConversation';
import { useOverlayManager } from './hooks/useOverlayManager';
import { useProvider } from './hooks/useProvider';
import { useScenario } from './hooks/useScenario';
import { useScrollState } from './hooks/useScrollState';
import { useTerminalKeyboard } from './hooks/useTerminalKeyboard';
import { useTickAnimation } from './hooks/useTickAnimation';
import { OverlayRouter } from './routes/OverlayRouter';
import { ExitScreen } from './screens/Exit/ExitScreen';
import { SetupWizard } from './screens/SetupWizard';
import { WelcomeScreen } from './screens/Welcome';
import type { CommandRunContext } from './services/api/CommandRegistry';
import { commandService } from './services/api/CommandService';
import { addSession } from './services/api/SessionRepository';
import { startupService } from './services/api/StartupService';
import type { TokenUsageStats } from './services/api/TokenUsageService';
import { tokenUsageService } from './services/api/TokenUsageService';
import { estimateTokensForEvents } from './services/api/tokenEstimationService';
import { loadUserProfile } from './services/api/userProfileService';
import { savePlanToFile } from './services/export/markdownExport';
import { modelStore } from './services/providers/ModelStore';
import { providerRepository } from './services/providers/ProviderRepository';
import type { SessionSummary } from './services/transport/WebSocketClient';
import { wsClient } from './services/transport/WebSocketClient';
import { useTheme } from './theme/ThemeContext';
import type { ScenarioEvent, ScenarioMode } from './types/scenario';
import type { AppStartupState } from './types/startup';
import { sanitizeSingleLine, truncateEnd } from './utils/text';
import { computeVisibleTurns } from './utils/turnWindow';

export interface RetryTarget {
  prompt: string;
  mode: ScenarioMode;
  model?: string;
}

export const App: React.FC = () => {
  const { theme } = useTheme();
  const [startupState, setStartupState] = useState<AppStartupState>(() => startupService.state);
  const tick = useTickAnimation(150, startupState.phase === 'loading');
  const [workspace, setWorkspace] = useState(() => process.cwd());
  useEffect(() => {
    setWorkspace(process.cwd());
  }, []);
  const [thinkingCollapsed, setThinkingCollapsed] = useState(() => loadUserProfile().settings.thinkingCollapsed);
  const [exitPhase, setExitPhase] = useState<'idle' | 'exiting'>('idle');

  useEffect(() => {
    startupService.initialize().then(setStartupState);
    const unsub = startupService.subscribe(setStartupState);
    return unsub;
  }, []);

  const toggleThinking = useCallback(() => setThinkingCollapsed((p) => !p), []);
  const [showPalette, setShowPalette] = useState(false);

  const [retryTarget, setRetryTarget] = useState<RetryTarget | null>(null);
  const handleRetryDismiss = useCallback(() => setRetryTarget(null), []);

  const {
    turns,
    completedTurns,
    activeTurn,
    totalTokens,
    staticKey,
    addTurn,
    completeActiveTurn,
    abortActiveTurn,
    markTurnSaved,
    clearTurns,
    compactTurns,
  } = useConversation();

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

  const { events, isRunning, startScenario, abort, eventsRef, lastSessionId, setActiveSessionId } = useScenario();
  const { activeProvider } = useProvider();
  const [tokenUsageStats, setTokenUsageStats] = useState<TokenUsageStats | null>(null);

  const refreshStats = useCallback(() => {
    tokenUsageService.fetchStats().then(setTokenUsageStats);
  }, []);

  useEffect(() => {
    if (startupState.phase === 'ready') {
      refreshStats();
    }
  }, [startupState.phase, refreshStats]);

  const liveTotalTokens = useMemo(() => {
    return totalTokens + (isRunning ? estimateTokensForEvents(events) : 0);
  }, [totalTokens, isRunning, events]);

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
    compactTurns();
    if (lastSessionId) {
      wsClient.contextCompact(lastSessionId).catch(() => {});
    }
  }, [compactTurns, lastSessionId]);

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
      savePlanToFile(targetEvents, targetTurn?.prompt || 'Plan Request', process.cwd(), 'implementation-plan.md');
      if (targetTurn) {
        markTurnSaved(targetTurn.id);
      }
    }
  }, [turns, events, isRunning, markTurnSaved]);

  const handleExit = useCallback(() => {
    setExitPhase('exiting');
  }, []);

  const handleSessionResume = useCallback(
    (sessionId: string, _summary: SessionSummary) => {
      setActiveSessionId(sessionId);
      clearTurns();
    },
    [setActiveSessionId, clearTurns],
  );

  const handleCancel = useCallback(() => {
    abort();
    abortActiveTurn();
    setRetryTarget(null);
  }, [abort, abortActiveTurn]);

  const commandCtx = useMemo<CommandRunContext>(
    () => ({
      openOverlay,
      clearTurns,
      compactTurns: handleCompact,
      clearTools: handleClearTools,
      setMode: handleModeSelect,
      openModelPicker: () => openOverlay('models'),
      openPalette: () => handleSetShowPalette(true),
      toggleThinking,
      savePlan: handleSavePlan,
      triggerExit: handleExit,
    }),
    [
      openOverlay,
      clearTurns,
      handleCompact,
      handleClearTools,
      handleModeSelect,
      handleSetShowPalette,
      toggleThinking,
      handleSavePlan,
      handleExit,
    ],
  );

  const handleSubmit = useCallback(
    (value: string) => {
      const trimmed = value.trim();
      if (!trimmed) return;
      if (trimmed.startsWith('/')) {
        clearInput();
        commandService.dispatchCommand(trimmed, commandCtx);
        return;
      }

      const sel = modelStore.current;
      const providerInfo = sel ? providerRepository.getProviderInfo(sel.providerID) : undefined;
      const selConfigured = Boolean(
        providerInfo &&
          (providerInfo.has_api_key || providerInfo.validation_status === 'validated' || providerInfo.is_active),
      );
      const selValid = Boolean(
        sel &&
          providerInfo &&
          selConfigured &&
          (providerInfo.models[sel.modelID] || providerInfo.model === sel.modelID),
      );
      const modelSel = selValid ? sel : null;
      const providerId = modelSel?.providerID ?? activeProvider.id;
      const modelId = modelSel?.modelID;

      addHistory(trimmed);
      addTurn(trimmed, selectedMode, modelId);
      clearInput();
      setRetryTarget(null);
      startScenario(trimmed, selectedMode, providerId, modelId, attachments);
    },
    [selectedMode, startScenario, activeProvider.id, addTurn, clearInput, commandCtx, addHistory, attachments],
  );

  useTerminalKeyboard({
    turns,
    isRunning,
    events,
    overlay,
    openOverlay,
    closeOverlay,
    closeAllOverlays,
    abort,
    abortActiveTurn,
    markTurnSaved,
    clearTurns,
    onToggleThinking: toggleThinking,
    scrollUp,
    scrollDown,
    scrollToTop,
    scrollToBottom,
    showPalette,
    setShowPalette: handleSetShowPalette,
    slashMenuOpen: showAutocomplete,
  });

  useEffect(() => {
    if (!isRunning && events.length > 0 && activeTurn && !activeTurn.isComplete) {
      const hadRecoverableError = eventsRef.current.some((e) => e.kind === 'error' && e.recoverable);
      if (hadRecoverableError) {
        setRetryTarget({
          prompt: activeTurn.prompt,
          mode: activeTurn.mode,
          model: activeTurn.model,
        });
      }
      completeActiveTurn(eventsRef.current);
      addSession(activeTurn.prompt).catch(() => {});
      refreshStats();
    }
  }, [isRunning, events, eventsRef, activeTurn, completeActiveTurn, refreshStats]);

  const handleAutocompleteSelectWithRouter = useCallback(
    (cmd: string) => {
      if (cmd.startsWith('/')) {
        clearInput();
        commandService.dispatchCommand(cmd, commandCtx);
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

  const visibleTurns = useMemo(
    () =>
      computeVisibleTurns({
        completedTurns,
        isUserScrolled: scrollState.isUserScrolled,
        isRunning,
        scrollOffset: scrollState.scrollOffset,
        viewportHeight: scrollState.viewportHeight,
      }),
    [completedTurns, scrollState.isUserScrolled, scrollState.scrollOffset, scrollState.viewportHeight, isRunning],
  );

  const firstVisibleIdx = visibleTurns.length > 0 ? completedTurns.indexOf(visibleTurns[0]) : completedTurns.length;
  const hiddenAbove = Math.max(0, completedTurns.length - visibleTurns.length - Math.max(0, firstVisibleIdx));
  const showScrollIndicator = scrollState.isUserScrolled && (isRunning || completedTurns.length > 0);

  if (startupState.phase === 'loading') {
    return (
      <Box
        flexDirection="column"
        paddingX={1}
        paddingTop={1}
        width="100%"
        justifyContent="center"
        alignItems="center"
        minHeight={5}
      >
        <Text color={theme.colors.text.muted}>
          {ASCII_SPINNER_FRAMES[tick % ASCII_SPINNER_FRAMES.length]} Initializing Zenith...
        </Text>
      </Box>
    );
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

        {scrollState.isUserScrolled && hiddenAbove > 0 && (
          <Box paddingX={1} marginBottom={1}>
            <Text color={theme.colors.text.muted} dimColor>
              ... {hiddenAbove} earlier turns hidden (scroll up to view)
            </Text>
          </Box>
        )}

        <Static key={staticKey} items={visibleTurns}>
          {(turn, idx) => (
            <Box key={turn.id} flexDirection="column" width="100%">
              {idx > 0 && (
                <Box marginTop={1} marginBottom={0} paddingX={1} width="100%">
                  <Text color={theme.colors.border.muted}>
                    {'─'.repeat(Math.min(process.stdout.columns ?? 80, 80))}
                  </Text>
                </Box>
              )}
              <Box marginTop={1} flexDirection="column" width="100%">
                <UserMessageBlock prompt={turn.prompt} />
                {turn.events.length > 0 && (
                  <ScenarioRenderer
                    events={turn.events}
                    isRunning={false}
                    isHistorical={true}
                    thinkingCollapsed={thinkingCollapsed}
                  />
                )}
              </Box>
            </Box>
          )}
        </Static>

        {isRunning && (
          <Box flexDirection="column" marginTop={1} width="100%">
            {scrollState.isUserScrolled ? (
              <Box paddingX={1}>
                <Text color={theme.colors.text.muted} dimColor>
                  ▸ Generating… (PgDn / End to follow the live output)
                </Text>
              </Box>
            ) : (
              <>
                {activeTurn && <UserMessageBlock prompt={activeTurn.prompt} />}
                <ScenarioRenderer
                  events={events}
                  isRunning={isRunning}
                  isHistorical={false}
                  thinkingCollapsed={thinkingCollapsed}
                />
              </>
            )}
          </Box>
        )}

        {!showFilePicker && !isOverlayOpen && !showPalette && (
          <Box flexDirection="column" width="100%">
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
              disabled={!!retryTarget}
              disabledMessage={retryTarget ? 'Choose an action above…' : undefined}
              attachments={attachments}
              onRemoveAttachment={removeAttachment}
              historyUp={historyUp}
              historyDown={historyDown}
              mode={selectedMode}
              totalTokens={liveTotalTokens}
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
            <FilePickerModal onSelectFile={insertFilePath} onClose={closeFilePicker} />
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
          tokenUsageStats={tokenUsageStats}
          onSelectMode={handleModeSelect}
          onClose={closeOverlay}
          onComplete={handleSetupComplete}
          onOpenProvider={handleOpenProvider}
          onResumeSession={handleSessionResume}
        />

        <SessionStatusBar
          mode={selectedMode}
          totalTokens={totalTokens}
          isRunning={isRunning}
          isOverlayOpen={isOverlayOpen}
          hasEvents={events.length > 0 || turns.length > 0}
          tokenUsageStats={tokenUsageStats}
        />
      </Box>
    </AppProvider>
  );
};
