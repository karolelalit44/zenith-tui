import { Box, Static, Text } from 'ink';
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ScenarioRenderer } from './components/Display/Scenario';
import { UserMessageBlock } from './components/Display/Scenario/UserMessageBlock';
import { ScrollIndicator } from './components/Display/ScrollIndicator';
import { SessionStatusBar } from './components/Display/SessionStatusBar';
import { AutocompleteDropdown } from './components/Input/AutocompleteDropdown';
import { CommandInput } from './components/Input/CommandInput';
import { FilePickerModal } from './components/Input/FilePicker/FilePickerModal';
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
import { SetupWizard } from './screens/SetupWizard';
import { WelcomeScreen } from './screens/Welcome';
import { commandService } from './services/api/CommandService';
import { addSession } from './services/api/SessionRepository';
import { startupService } from './services/api/StartupService';
import type { TokenUsageStats } from './services/api/TokenUsageService';
import { tokenUsageService } from './services/api/TokenUsageService';
import { estimateTokensForEvents } from './services/api/tokenEstimationService';
import { loadUserProfile } from './services/api/userProfileService';
import { providerRepository } from './services/providers/ProviderRepository';
import { wsClient } from './services/transport/WebSocketClient';
import { useTheme } from './theme/ThemeContext';
import type { ScenarioEvent } from './types/scenario';
import type { AppStartupState } from './types/startup';

export const App: React.FC = () => {
  const { theme } = useTheme();
  const [startupState, setStartupState] = useState<AppStartupState>(() => startupService.state);
  const tick = useTickAnimation(150, startupState.phase === 'loading');
  const [workspace, setWorkspace] = useState(() => process.cwd());
  useEffect(() => {
    setWorkspace(process.cwd());
  }, []);
  const [thinkingCollapsed, setThinkingCollapsed] = useState(() => loadUserProfile().settings.thinkingCollapsed);

  useEffect(() => {
    startupService.initialize().then(setStartupState);
    const unsub = startupService.subscribe(setStartupState);
    return unsub;
  }, []);

  const toggleThinking = useCallback(() => setThinkingCollapsed((p) => !p), []);

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

  // First-run empty state: when startup is ready but no provider has an API key,
  // auto-open the provider picker so the user can connect one.
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

  const { events, isRunning, startScenario, abort, activeConfirmation, respondConfirmation, eventsRef, lastSessionId } =
    useScenario();
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
    const estimatedHeight = completedTurns.length * 15 + (isRunning ? events.length * 2 : 0);
    updateContentHeight(estimatedHeight);
  }, [completedTurns.length, events.length, isRunning, updateContentHeight]);

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

  const handleSubmit = useCallback(
    (value: string) => {
      const trimmed = value.trim();
      if (!trimmed) return;
      if (trimmed.startsWith('/')) {
        clearInput();
        commandService.dispatchCommand(trimmed, {
          openOverlay,
          clearTurns,
          compactTurns: handleCompact,
          clearTools: handleClearTools,
          setMode: handleModeSelect,
        });
        return;
      }
      addHistory(trimmed);
      addTurn(trimmed, selectedMode);
      clearInput();
      startScenario(trimmed, selectedMode, activeProvider.id);
    },
    [
      selectedMode,
      startScenario,
      activeProvider.id,
      addTurn,
      clearInput,
      openOverlay,
      clearTurns,
      handleCompact,
      handleClearTools,
      handleModeSelect,
      addHistory,
    ],
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
    activeConfirmation,
    respondConfirmation,
    scrollUp,
    scrollDown,
    scrollToTop,
    scrollToBottom,
  });

  useEffect(() => {
    if (!isRunning && events.length > 0 && activeTurn && !activeTurn.isComplete) {
      completeActiveTurn(eventsRef.current);
      addSession(activeTurn.prompt).catch(() => {});
      refreshStats();
    }
  }, [isRunning, events, eventsRef, activeTurn, completeActiveTurn, refreshStats]);

  const handleAutocompleteSelectWithRouter = useCallback(
    (cmd: string) => {
      if (cmd.startsWith('/')) {
        clearInput();
        commandService.dispatchCommand(cmd, {
          openOverlay,
          clearTurns,
          compactTurns: handleCompact,
          clearTools: handleClearTools,
          setMode: handleModeSelect,
        });
      } else {
        handleAutocompleteSelect(cmd);
      }
    },
    [clearInput, openOverlay, clearTurns, handleCompact, handleClearTools, handleModeSelect, handleAutocompleteSelect],
  );

  const handleRetry = useCallback(() => {
    if (activeTurn && !isRunning) startScenario(activeTurn.prompt, activeTurn.mode, activeProvider.id);
  }, [activeTurn, isRunning, startScenario, activeProvider.id]);

  const handleSetupComplete = useCallback(() => {
    setStartupState({ phase: 'ready', result: startupState.result, error: null });
  }, [startupState]);

  // Calculate visible turns based on scroll offset (must be before conditional returns)
  const visibleTurns = useMemo(() => {
    if (!scrollState.isUserScrolled || isRunning) {
      return completedTurns;
    }

    const viewportTurns = scrollState.viewportHeight / 15;
    const startIdx = Math.floor(scrollState.scrollOffset / 15);
    const endIdx = Math.min(completedTurns.length, startIdx + Math.ceil(viewportTurns) + 2);

    return completedTurns.slice(Math.max(0, startIdx), endIdx);
  }, [completedTurns, scrollState.isUserScrolled, scrollState.scrollOffset, scrollState.viewportHeight, isRunning]);

  const hiddenAbove = completedTurns.length - visibleTurns.length - (completedTurns.indexOf(visibleTurns[0]) || 0);
  const showScrollIndicator = scrollState.isUserScrolled && (isRunning || completedTurns.length > 0);

  // Loading screen
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

  // Setup wizard
  if (startupState.phase === 'setup' || startupState.phase === 'error') {
    return (
      <Box flexDirection="column" paddingX={1} paddingTop={1} width="100%">
        <SetupWizard startupState={startupState} onComplete={handleSetupComplete} />
      </Box>
    );
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
      activeConfirmation={activeConfirmation}
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
            {activeTurn && <UserMessageBlock prompt={activeTurn.prompt} />}
            <ScenarioRenderer
              events={events}
              isRunning={isRunning}
              isHistorical={false}
              thinkingCollapsed={thinkingCollapsed}
              onRetry={handleRetry}
            />
          </Box>
        )}

        {!showAutocomplete && !showFilePicker && !isOverlayOpen && (
          <CommandInput
            input={input}
            onInputChange={handleInputChange}
            onSubmit={handleSubmit}
            disabled={isRunning}
            attachments={attachments}
            onRemoveAttachment={removeAttachment}
            historyUp={historyUp}
            historyDown={historyDown}
            mode={selectedMode}
            totalTokens={liveTotalTokens}
            isRunning={isRunning}
            tokenUsageStats={tokenUsageStats}
            workspaceName={workspace}
          />
        )}

        {showAutocomplete && (
          <Box marginTop={1} width="100%">
            <AutocompleteDropdown
              input={input}
              onSelect={handleAutocompleteSelectWithRouter}
              onClose={closeAutocomplete}
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
