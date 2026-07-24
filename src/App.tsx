import { Box, Text } from 'ink';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { PromptHeader } from './components/Display/PromptHeader';
import { ScenarioRenderer } from './components/Display/Scenario';
import { SessionStatusBar } from './components/Display/SessionStatusBar';
import { AutocompleteDropdown } from './components/Input/AutocompleteDropdown';
import { CommandInput } from './components/Input/CommandInput';
import { FilePickerModal } from './components/Input/FilePicker/FilePickerModal';
import { ASCII_SPINNER_FRAMES } from './constants/animation';
import { useAutocomplete } from './hooks/useAutocomplete';
import { useConversation } from './hooks/useConversation';
import { useOverlayManager } from './hooks/useOverlayManager';
import { useScenario } from './hooks/useScenario';
import { useTerminalKeyboard } from './hooks/useTerminalKeyboard';
import { useTickAnimation } from './hooks/useTickAnimation';
import { AddDirModal } from './screens/AddDir/AddDirModal';
import { ContextModal } from './screens/Context/ContextModal';
import { HelpModal } from './screens/Help/HelpModal';
import { ModeSelectScreen } from './screens/ModeSelect';
import { ProvidersScreen } from './screens/Providers/ProvidersScreen';
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
    activeTurn,
    totalTokens,
    addTurn,
    completeActiveTurn,
    abortActiveTurn,
    markTurnSaved,
    clearTurns,
    compactTurns,
  } = useConversation();
  const { selectedMode, overlay, isOverlayOpen, openOverlay, closeOverlay, handleModeSelect } = useOverlayManager();
  const {
    input,
    showAutocomplete,
    showFilePicker,
    handleInputChange,
    handleAutocompleteSelect,
    clearInput,
    insertFilePath,
    closeFilePicker,
    addHistory,
  } = useAutocomplete();
  const { events, isRunning, startScenario, abort } = useScenario();

  const [scrollOffset, setScrollOffset] = useState(0);
  const MAX_VISIBLE_COMPLETED = 8;
  const prevTurnCountRef = useRef(turns.length);
  const suppressSubmitRef = useRef(false);

  const insertNewline = useCallback(() => {
    suppressSubmitRef.current = true;
    handleInputChange(`${input}\n`);
  }, [input, handleInputChange]);

  useEffect(() => {
    if (turns.length > prevTurnCountRef.current) {
      setScrollOffset(0);
    }
    prevTurnCountRef.current = turns.length;
  }, [turns.length]);

  const completedTurns = isRunning ? turns.slice(0, -1) : turns;
  const hiddenAbove = Math.max(0, completedTurns.length - MAX_VISIBLE_COMPLETED - scrollOffset);
  const visibleTurns = completedTurns.slice(
    Math.max(0, completedTurns.length - MAX_VISIBLE_COMPLETED - scrollOffset),
    completedTurns.length - scrollOffset,
  );

  const scrollUp = useCallback(() => {
    setScrollOffset((prev) => Math.min(prev + 3, Math.max(0, completedTurns.length - MAX_VISIBLE_COMPLETED)));
  }, [completedTurns.length]);

  const scrollDown = useCallback(() => {
    setScrollOffset((prev) => Math.max(0, prev - 3));
  }, []);

  const isIdle = !isRunning && !isOverlayOpen;

  useTerminalKeyboard({
    turns,
    isRunning,
    events,
    overlay,
    openOverlay,
    closeOverlay,
    abort,
    abortActiveTurn,
    markTurnSaved,
    onToggleThinking: toggleThinking,
    onScrollUp: scrollUp,
    onScrollDown: scrollDown,
    onInsertNewline: insertNewline,
  });

  useEffect(() => {
    if (!isRunning && events.length > 0 && activeTurn && !activeTurn.isComplete) {
      completeActiveTurn(events);
      addSession(activeTurn.prompt);
    }
  }, [isRunning, events, activeTurn, completeActiveTurn]);

  const dispatchCommand = useCallback(
    (cmd: string) => {
      clearInput();
      commandService.dispatchCommand(cmd, {
        openOverlay,
        clearTurns,
        compactTurns,
        setMode: handleModeSelect,
      });
    },
    [clearInput, openOverlay, clearTurns, compactTurns, handleModeSelect],
  );

  const handleSubmit = useCallback(
    (value: string) => {
      if (suppressSubmitRef.current) {
        suppressSubmitRef.current = false;
        return;
      }
      const trimmed = value.trim();
      if (!trimmed) return;

      if (trimmed.startsWith('/')) {
        dispatchCommand(trimmed);
        return;
      }

      addHistory(trimmed);
      addTurn(trimmed, selectedMode);
      clearInput();
      startScenario(trimmed, selectedMode);
    },
    [selectedMode, startScenario, addTurn, clearInput, dispatchCommand, addHistory],
  );

  const handleAutocompleteSelectWithRouter = useCallback(
    (cmd: string) => {
      if (cmd.startsWith('/')) {
        dispatchCommand(cmd);
      } else {
        handleAutocompleteSelect(cmd);
      }
    },
    [dispatchCommand, handleAutocompleteSelect],
  );

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
        <SetupWizard
          startupState={startupState}
          onComplete={() => {
            setStartupState({ phase: 'ready', result: startupState.result, error: null });
          }}
        />
      </Box>
    );
  }

  return (
    <Box flexDirection="column" paddingX={1} paddingTop={1} width="100%">
      {/* Welcome Screen - always visible */}
      <WelcomeScreen workspace={workspace} />

      {/* Conversation turns */}
      {hiddenAbove > 0 && (
        <Box marginTop={1}>
          <Text color={theme.colors.text.muted} italic>
            ↑ {hiddenAbove} earlier turn{hiddenAbove > 1 ? 's' : ''} hidden (PgUp to scroll)
          </Text>
        </Box>
      )}

      {visibleTurns.map((turn) => (
        <Box key={turn.id} flexDirection="column" marginTop={1}>
          <PromptHeader prompt={turn.prompt} mode={turn.mode} timestamp={turn.timestamp} />
          {turn.events.length > 0 && (
            <ScenarioRenderer
              events={turn.events}
              isRunning={false}
              isHistorical={true}
              thinkingCollapsed={thinkingCollapsed}
            />
          )}
        </Box>
      ))}

      {/* Scroll indicator */}
      {scrollOffset > 0 && (
        <Box marginTop={1}>
          <Text color={theme.colors.text.muted} italic>
            ↓ Showing older turns (PgDn to scroll down)
          </Text>
        </Box>
      )}

      {/* Currently running scenario */}
      {isRunning && (
        <Box flexDirection="column" marginTop={1}>
          {activeTurn && (
            <PromptHeader prompt={activeTurn.prompt} mode={activeTurn.mode} timestamp={activeTurn.timestamp} />
          )}
          <ScenarioRenderer
            events={events}
            isRunning={isRunning}
            isHistorical={false}
            thinkingCollapsed={thinkingCollapsed}
          />
        </Box>
      )}

      {/* Input box - visible when idle and no overlays */}
      {isIdle && !showAutocomplete && !showFilePicker && (
        <CommandInput
          input={input}
          selectedMode={selectedMode}
          onInputChange={handleInputChange}
          onSubmit={handleSubmit}
        />
      )}

      {/* Slash Command Palette */}
      {showAutocomplete && (
        <Box marginTop={1}>
          <AutocompleteDropdown input={input} onSelect={handleAutocompleteSelectWithRouter} />
        </Box>
      )}

      {/* File Picker Modal */}
      {showFilePicker && (
        <Box marginTop={1}>
          <FilePickerModal onSelectFile={insertFilePath} onClose={closeFilePicker} />
        </Box>
      )}

      {/* Session Status Bar - always visible when there are turns or running */}
      {(turns.length > 0 || isRunning) && !showAutocomplete && !showFilePicker && (
        <SessionStatusBar
          mode={selectedMode}
          totalTokens={totalTokens}
          isRunning={isRunning}
          workspaceName={workspace}
        />
      )}

      {/* Overlays & Modals */}
      {overlay === 'mode' && (
        <Box flexDirection="column" marginTop={1}>
          <ModeSelectScreen currentMode={selectedMode} onSelect={handleModeSelect} onClose={closeOverlay} />
        </Box>
      )}

      {overlay === 'help' && (
        <Box flexDirection="column" marginTop={1}>
          <HelpModal onClose={closeOverlay} />
        </Box>
      )}

      {overlay === 'settings' && (
        <Box flexDirection="column" marginTop={1}>
          <SettingsModal onClose={closeOverlay} />
        </Box>
      )}

      {overlay === 'context' && (
        <Box flexDirection="column" marginTop={1}>
          <ContextModal totalTokens={totalTokens} runningEvents={events} onClose={closeOverlay} />
        </Box>
      )}

      {overlay === 'add-dir' && (
        <Box flexDirection="column" marginTop={1}>
          <AddDirModal currentWorkspace={workspace} onSelectDir={(dir) => setWorkspace(dir)} onClose={closeOverlay} />
        </Box>
      )}

      {overlay === 'provider' && (
        <Box flexDirection="column" marginTop={1}>
          <ProvidersScreen onClose={closeOverlay} />
        </Box>
      )}
    </Box>
  );
};
