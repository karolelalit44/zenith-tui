import { Box, Text } from 'ink';
import TextInput from 'ink-text-input';
import React, { useCallback, useEffect } from 'react';
import { PromptHeader } from './components/Display/PromptHeader';
import { ScenarioRenderer } from './components/Display/Scenario';
import { SessionStatusBar } from './components/Display/SessionStatusBar';
import { AutocompleteDropdown } from './components/Input/AutocompleteDropdown';
import { FilePickerModal } from './components/Input/FilePicker/FilePickerModal';
import { useAutocomplete } from './hooks/useAutocomplete';
import { useConversation } from './hooks/useConversation';
import { useModeSelector } from './hooks/useModeSelector';
import { useScenario } from './hooks/useScenario';
import { useTerminalKeyboard } from './hooks/useTerminalKeyboard';
import { ModeSelectScreen } from './screens/ModeSelect';
import { WelcomeScreen } from './screens/Welcome';
import { useTheme } from './theme/ThemeContext';
import type { Persona } from './types';

export const App: React.FC = () => {
  const { theme } = useTheme();
  const persona: Persona = 'architect';
  const { turns, activeTurn, totalTokens, addTurn, completeActiveTurn, abortActiveTurn, markTurnSaved } =
    useConversation();
  const { selectedMode, overlay, isOverlayOpen, openModeSelector, closeOverlay, handleModeSelect } = useModeSelector();
  const {
    input,
    showAutocomplete,
    showFilePicker,
    handleInputChange,
    handleAutocompleteSelect,
    clearInput,
    insertFilePath,
    closeFilePicker,
  } = useAutocomplete();
  const { events, isRunning, startScenario, abort } = useScenario();

  const isIdle = !isRunning && !isOverlayOpen;

  useTerminalKeyboard({
    turns,
    isRunning,
    events,
    overlay,
    closeOverlay,
    abort,
    abortActiveTurn,
    markTurnSaved,
  });

  useEffect(() => {
    if (!isRunning && events.length > 0 && activeTurn && !activeTurn.isComplete) {
      completeActiveTurn(events);
    }
  }, [isRunning, events, activeTurn, completeActiveTurn]);

  const handleSubmit = useCallback(
    (value: string) => {
      const trimmed = value.trim();
      if (!trimmed) return;

      if (trimmed === '/mode') {
        openModeSelector();
        clearInput();
        return;
      }

      if (trimmed.startsWith('/')) {
        clearInput();
        return;
      }

      addTurn(trimmed, selectedMode);
      clearInput();
      startScenario(trimmed, selectedMode);
    },
    [selectedMode, startScenario, addTurn, clearInput, openModeSelector],
  );

  const handleAutocompleteSelectWithMode = useCallback(
    (cmd: string) => {
      if (cmd === '/mode') {
        openModeSelector();
        clearInput();
      } else {
        handleAutocompleteSelect(cmd);
      }
    },
    [openModeSelector, clearInput, handleAutocompleteSelect],
  );

  return (
    <Box flexDirection="column" paddingX={1} paddingTop={1} width="100%">
      {/* Welcome Screen - always visible */}
      <WelcomeScreen persona={persona} mode={selectedMode} />

      {/* Conversation turns */}
      {turns.map((turn) => (
        <Box key={turn.id} flexDirection="column" marginTop={1}>
          <PromptHeader prompt={turn.prompt} mode={turn.mode} timestamp={turn.timestamp} />
          {turn.events.length > 0 && <ScenarioRenderer events={turn.events} isRunning={false} isHistorical={true} />}
        </Box>
      ))}

      {/* Currently running scenario */}
      {isRunning && (
        <Box flexDirection="column" marginTop={1}>
          {activeTurn && (
            <PromptHeader prompt={activeTurn.prompt} mode={activeTurn.mode} timestamp={activeTurn.timestamp} />
          )}
          <ScenarioRenderer events={events} isRunning={isRunning} isHistorical={false} />
        </Box>
      )}

      {/* Input box & Session Status Bar - visible when idle */}
      {isIdle && (
        <Box flexDirection="column" marginTop={1}>
          <Box flexDirection="row">
            <Text color={theme.colors.text.muted}>{'> '}</Text>
            <TextInput
              value={input}
              onChange={handleInputChange}
              onSubmit={handleSubmit}
              placeholder="Ask anything..."
              focus={true}
            />
          </Box>

          {/* Slash Command Palette */}
          {showAutocomplete && (
            <Box marginTop={1}>
              <AutocompleteDropdown input={input} onSelect={handleAutocompleteSelectWithMode} />
            </Box>
          )}

          {/* File Picker Modal */}
          {showFilePicker && (
            <Box marginTop={1}>
              <FilePickerModal onSelectFile={insertFilePath} onClose={closeFilePicker} />
            </Box>
          )}

          {/* Claude Code CLI Session Status Bar */}
          {!showAutocomplete && !showFilePicker && (
            <SessionStatusBar mode={selectedMode} totalTokens={totalTokens} isRunning={isRunning} />
          )}
        </Box>
      )}

      {/* Mode select overlay */}
      {overlay === 'mode' && (
        <Box flexDirection="column" marginTop={1}>
          <ModeSelectScreen currentMode={selectedMode} onSelect={handleModeSelect} onClose={closeOverlay} />
        </Box>
      )}
    </Box>
  );
};
