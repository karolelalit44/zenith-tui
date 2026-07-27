import { Box, Static, Text } from 'ink';
import React, { useCallback, useEffect, useState } from 'react';
import { ScenarioRenderer } from './components/Display/Scenario';
import { UserMessageBlock } from './components/Display/Scenario/UserMessageBlock';
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
import { useTerminalKeyboard } from './hooks/useTerminalKeyboard';
import { useTickAnimation } from './hooks/useTickAnimation';
import { ContextModal } from './screens/Context/ContextModal';
import { HelpModal } from './screens/Help/HelpModal';
import { ModeSelectScreen } from './screens/ModeSelect';
import { SettingsModal } from './screens/Settings/SettingsModal';
import { SetupWizard } from './screens/SetupWizard';
import { WelcomeScreen } from './screens/Welcome';
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
  const [workspace, setWorkspace] = useState(() => process.cwd());
  const [thinkingCollapsed, setThinkingCollapsed] = useState(() => loadUserProfile().settings.thinkingCollapsed);

  useEffect(() => {
    startupService.initialize().then(setStartupState);
    const unsub = startupService.subscribe(setStartupState);
    return unsub;
  }, []);

  const toggleThinking = useCallback(() => {
    setThinkingCollapsed((prev: boolean) => !prev);
  }, []);
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
        commandService.dispatchCommand(trimmed, {
          openOverlay,
          clearTurns,
          compactTurns,
          setMode: handleModeSelect,
        });
        return;
      }

      addHistory(trimmed);
      addTurn(trimmed, selectedMode);
      clearInput();
      startScenario(trimmed, selectedMode);
    },
    [
      selectedMode,
      startScenario,
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
        commandService.dispatchCommand(cmd, {
          openOverlay,
          clearTurns,
          compactTurns,
          setMode: handleModeSelect,
        });
      } else {
        handleAutocompleteSelect(cmd);
      }
    },
    [clearInput, openOverlay, clearTurns, compactTurns, handleModeSelect, handleAutocompleteSelect],
  );

  const handleRetry = useCallback(() => {
    if (activeTurn && !isRunning) {
      startScenario(activeTurn.prompt, activeTurn.mode);
    }
  }, [activeTurn, isRunning, startScenario]);

  const handleSetupComplete = useCallback(() => {
    setStartupState({ phase: 'ready', result: startupState.result, error: null });
  }, [startupState]);

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
        {turns.length === 0 && !isRunning && (
          <>
            <WelcomeScreen workspace={workspace} />
            <Box flexDirection="column" paddingX={2} marginTop={1} marginBottom={1}>
              <Text color={theme.colors.text.muted} bold>
                Try asking:
              </Text>
              <Box flexDirection="column" marginTop={1} paddingLeft={1}>
                {[
                  'Help me understand this codebase',
                  'Run the test suite and show results',
                  'Create a new module with proper structure',
                ].map((suggestion, idx) => (
                  <Box key={idx} flexDirection="row" marginBottom={0}>
                    <Text color={theme.colors.status.accent}>{idx + 1}. </Text>
                    <Text color={theme.colors.text.ethereal}>{suggestion}</Text>
                  </Box>
                ))}
              </Box>
            </Box>
          </>
        )}

        {/* Completed turns — rendered once via Static, immune to live event re-renders */}
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

        {/* Currently running scenario */}
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

        {/* Input box — hidden while any overlay/modal is active to prevent keypress leakage */}
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
          />
        )}

        {/* Slash Command Palette */}
        {showAutocomplete && (
          <Box marginTop={1} width="100%">
            <AutocompleteDropdown
              input={input}
              onSelect={handleAutocompleteSelectWithRouter}
              onClose={closeAutocomplete}
            />
          </Box>
        )}

        {/* File Picker Modal */}
        {showFilePicker && (
          <Box marginTop={1} width="100%">
            <FilePickerModal onSelectFile={insertFilePath} onClose={closeFilePicker} />
          </Box>
        )}

        {/* Session Status Bar removed as details are in CommandInput */}

        {/* Overlays & Modals */}
        {overlay === 'mode' && (
          <Box flexDirection="column" marginTop={1} width="100%">
            <ModeSelectScreen currentMode={selectedMode} onSelect={handleModeSelect} onClose={closeOverlay} />
          </Box>
        )}

        {overlay === 'help' && (
          <Box flexDirection="column" marginTop={1} width="100%">
            <HelpModal onClose={closeOverlay} />
          </Box>
        )}

        {overlay === 'settings' && (
          <Box flexDirection="column" marginTop={1} width="100%">
            <SettingsModal onClose={closeOverlay} />
          </Box>
        )}

        {overlay === 'context' && (
          <Box flexDirection="column" marginTop={1} width="100%">
            <ContextModal totalTokens={totalTokens} runningEvents={events} onClose={closeOverlay} />
          </Box>
        )}

        {overlay === 'provider' && (
          <Box flexDirection="column" marginTop={1} width="100%">
            <SetupWizard startupState={startupState} onComplete={closeOverlay} mode="reconfigure" />
          </Box>
        )}
      </Box>
    </AppProvider>
  );
};
