import { Box, Static, Text } from 'ink';
import React, { useCallback, useEffect, useState } from 'react';
import { ScenarioRenderer } from './components/Display/Scenario';
import { UserMessageBlock } from './components/Display/Scenario/UserMessageBlock';
import { AutocompleteDropdown } from './components/Input/AutocompleteDropdown';
import { CommandInput } from './components/Input/CommandInput';
import { FilePickerModal } from './components/Input/FilePicker/FilePickerModal';
import { WelcomeScreen } from './screens/Welcome';
import { ASCII_SPINNER_FRAMES } from './constants/animation';
import { AppProvider } from './context/AppContext';
import { useAutocomplete } from './hooks/useAutocomplete';
import { useConversation } from './hooks/useConversation';
import { useOverlayManager } from './hooks/useOverlayManager';
import { useProvider } from './hooks/useProvider';
import { useScenario } from './hooks/useScenario';
import { useTerminalKeyboard } from './hooks/useTerminalKeyboard';
import { useTickAnimation } from './hooks/useTickAnimation';
import { OverlayRouter } from './routes/OverlayRouter';
import { SetupWizard } from './screens/SetupWizard';
import { commandService } from './services/data/CommandService';
import { addSession } from './services/data/SessionRepository';
import { startupService } from './services/data/StartupService';
import { loadUserProfile } from './services/data/userProfileService';
import { useTheme } from './theme/ThemeContext';
import type { AppStartupState } from './types/startup';

export const App: React.FC = () => {
  const { theme } = useTheme();
  const [startupState, setStartupState] = useState<AppStartupState>(() => startupService.state);
  const tick = useTickAnimation(150, startupState.phase === 'loading');
  const [workspace, _setWorkspace] = useState(() => process.cwd());
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

  const { selectedMode, overlay, isOverlayOpen, openOverlay, closeOverlay, closeAllOverlays, handleModeSelect } =
    useOverlayManager();

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

  const { events, isRunning, startScenario, abort, activeConfirmation, respondConfirmation } = useScenario();
  const { activeProvider } = useProvider();

  const handleSubmit = useCallback(
    (value: string) => {
      const trimmed = value.trim();
      if (!trimmed) return;
      if (trimmed.startsWith('/')) {
        clearInput();
        commandService.dispatchCommand(trimmed, { openOverlay, clearTurns, compactTurns, setMode: handleModeSelect });
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
      compactTurns,
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
  });

  useEffect(() => {
    if (!isRunning && events.length > 0 && activeTurn && !activeTurn.isComplete) {
      completeActiveTurn(events);
      addSession(activeTurn.prompt);
    }
  }, [isRunning, events, activeTurn, completeActiveTurn]);

  const handleAutocompleteSelectWithRouter = useCallback(
    (cmd: string) => {
      if (cmd.startsWith('/')) {
        clearInput();
        commandService.dispatchCommand(cmd, { openOverlay, clearTurns, compactTurns, setMode: handleModeSelect });
      } else {
        handleAutocompleteSelect(cmd);
      }
    },
    [clearInput, openOverlay, clearTurns, compactTurns, handleModeSelect, handleAutocompleteSelect],
  );

  const handleRetry = useCallback(() => {
    if (activeTurn && !isRunning) startScenario(activeTurn.prompt, activeTurn.mode, activeProvider.id);
  }, [activeTurn, isRunning, startScenario, activeProvider.id]);

  const handleSetupComplete = useCallback(() => {
    setStartupState({ phase: 'ready', result: startupState.result, error: null });
  }, [startupState]);

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

        <Static key={staticKey} items={completedTurns}>
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
            totalTokens={totalTokens}
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

        <OverlayRouter
          overlay={overlay}
          isOverlayOpen={isOverlayOpen}
          selectedMode={selectedMode}
          totalTokens={totalTokens}
          events={events}
          startupState={startupState}
          onSelectMode={handleModeSelect}
          onClose={closeOverlay}
          onComplete={handleSetupComplete}
        />
      </Box>
    </AppProvider>
  );
};
