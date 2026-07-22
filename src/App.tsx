import { Box, Text } from 'ink';
import TextInput from 'ink-text-input';
import React, { useCallback, useEffect, useState } from 'react';
import { PromptHeader } from './components/Display/PromptHeader';
import { ScenarioRenderer } from './components/Display/Scenario';
import { SessionStatusBar } from './components/Display/SessionStatusBar';
import { AutocompleteDropdown } from './components/Input/AutocompleteDropdown';
import { FilePickerModal } from './components/Input/FilePicker/FilePickerModal';
import { DEFAULT_WORKSPACE } from './constants';
import { useAutocomplete } from './hooks/useAutocomplete';
import { useConversation } from './hooks/useConversation';
import { useOverlayManager } from './hooks/useOverlayManager';
import { usePersona } from './hooks/usePersona';
import { useScenario } from './hooks/useScenario';
import { useTerminalKeyboard } from './hooks/useTerminalKeyboard';
import { AddDirModal } from './screens/AddDir/AddDirModal';
import { AgentsModal } from './screens/Agents/AgentsModal';
import { ContextModal } from './screens/Context/ContextModal';
import { HelpModal } from './screens/Help/HelpModal';
import { ModeSelectScreen } from './screens/ModeSelect';
import { PersonaSelectModal } from './screens/PersonaSelect/PersonaSelectModal';
import { PluginsModal } from './screens/Plugins/PluginsModal';
import { SettingsModal } from './screens/Settings/SettingsModal';
import { WelcomeScreen } from './screens/Welcome';
import { SessionRepository } from './services/data/SessionRepository';
import { useTheme } from './theme/ThemeContext';

export const App: React.FC = () => {
  const { theme } = useTheme();
  const { persona, setPersona } = usePersona('architect');
  const [workspace, setWorkspace] = useState(DEFAULT_WORKSPACE);
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
  });

  useEffect(() => {
    if (!isRunning && events.length > 0 && activeTurn && !activeTurn.isComplete) {
      completeActiveTurn(events);
      SessionRepository.addSession(activeTurn.prompt, persona);
    }
  }, [isRunning, events, activeTurn, completeActiveTurn, persona]);

  const dispatchCommand = useCallback(
    (cmd: string) => {
      const lower = cmd.trim().toLowerCase();
      clearInput();

      switch (lower) {
        case '/mode':
          openOverlay('mode');
          break;
        case '/help':
          openOverlay('help');
          break;
        case '/persona':
          openOverlay('persona');
          break;
        case '/settings':
        case '/theme':
          openOverlay('settings');
          break;
        case '/context':
          openOverlay('context');
          break;
        case '/add-dir':
          openOverlay('add-dir');
          break;
        case '/agents':
          openOverlay('agents');
          break;
        case '/plugin':
        case '/plugins':
          openOverlay('plugin');
          break;
        case '/clear':
          clearTurns();
          break;
        case '/compact':
          compactTurns();
          break;
        default:
          break;
      }
    },
    [clearInput, openOverlay, clearTurns, compactTurns],
  );

  const handleSubmit = useCallback(
    (value: string) => {
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

  return (
    <Box flexDirection="column" paddingX={1} paddingTop={1} width="100%">
      {/* Welcome Screen - always visible */}
      <WelcomeScreen persona={persona} mode={selectedMode} workspace={workspace} />

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
              <AutocompleteDropdown input={input} onSelect={handleAutocompleteSelectWithRouter} />
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

      {overlay === 'persona' && (
        <Box flexDirection="column" marginTop={1}>
          <PersonaSelectModal
            currentPersona={persona}
            onSelect={(p) => {
              setPersona(p);
              closeOverlay();
            }}
            onClose={closeOverlay}
          />
        </Box>
      )}

      {overlay === 'settings' && (
        <Box flexDirection="column" marginTop={1}>
          <SettingsModal onClose={closeOverlay} />
        </Box>
      )}

      {overlay === 'context' && (
        <Box flexDirection="column" marginTop={1}>
          <ContextModal totalTokens={totalTokens} onClose={closeOverlay} />
        </Box>
      )}

      {overlay === 'add-dir' && (
        <Box flexDirection="column" marginTop={1}>
          <AddDirModal currentWorkspace={workspace} onSelectDir={(dir) => setWorkspace(dir)} onClose={closeOverlay} />
        </Box>
      )}

      {overlay === 'agents' && (
        <Box flexDirection="column" marginTop={1}>
          <AgentsModal onClose={closeOverlay} />
        </Box>
      )}

      {overlay === 'plugin' && (
        <Box flexDirection="column" marginTop={1}>
          <PluginsModal onClose={closeOverlay} />
        </Box>
      )}
    </Box>
  );
};
