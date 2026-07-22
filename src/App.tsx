import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { Box, Text, useInput } from 'ink';
import TextInput from 'ink-text-input';
import { WelcomeScreen } from './screens/Welcome';
import { ModeSelectScreen } from './screens/ModeSelect';
import { ScenarioRenderer } from './components/Display/Scenario';
import { SessionStatusBar } from './components/Display/SessionStatusBar';
import { AutocompleteDropdown } from './components/Input/AutocompleteDropdown';
import { useTheme } from './theme/ThemeContext';
import { useScenario } from './hooks/useScenario';
import { Persona, ScenarioMode, ScenarioEvent } from './types';
import { savePlanToFile } from './services/export/markdownExport';

type OverlayState = 'none' | 'mode';

interface ConversationTurn {
  id: string;
  prompt: string;
  mode: ScenarioMode;
  events: ScenarioEvent[];
  isComplete: boolean;
}

const MOCK_TOKENS_PER_TURN = 1247;

import { FilePickerModal } from './components/Input/FilePicker/FilePickerModal';

export const App: React.FC = () => {
  const { theme } = useTheme();
  const [persona] = useState<Persona>('architect');
  const [selectedMode, setSelectedMode] = useState<ScenarioMode>('build');
  const [input, setInput] = useState('');
  const [overlay, setOverlay] = useState<OverlayState>('none');
  const [turns, setTurns] = useState<ConversationTurn[]>([]);
  const [showAutocomplete, setShowAutocomplete] = useState(false);
  const [showFilePicker, setShowFilePicker] = useState(false);

  const { events, isRunning, startScenario, abort } = useScenario();

  const activeTurn = turns.length > 0 ? turns[turns.length - 1] : null;
  const isIdle = !isRunning && overlay === 'none';

  const totalTokens = useMemo(() => {
    return turns.filter(t => t.isComplete).length * MOCK_TOKENS_PER_TURN;
  }, [turns]);

  const handleInputChange = useCallback((val: string) => {
    setInput(val);
    if (val.startsWith('/')) {
      setShowAutocomplete(true);
      setShowFilePicker(false);
    } else if (val.startsWith('@')) {
      setShowFilePicker(true);
      setShowAutocomplete(false);
    } else {
      setShowAutocomplete(false);
      setShowFilePicker(false);
    }
  }, []);

  const [scrollOffset, setScrollOffset] = useState(0);

  useEffect(() => {
    // Enable extended VT/SGR/Urxvt mouse wheel and touchpad tracking in terminal
    try {
      process.stdout.write('\x1B[?1000h\x1B[?1002h\x1B[?1006h\x1B[?1015h');
    } catch (_e) {}

    return () => {
      try {
        process.stdout.write('\x1B[?1000l\x1B[?1002l\x1B[?1006l\x1B[?1015l');
      } catch (_e) {}
    };
  }, []);

  useInput((char, key) => {
    const isTouchpadOrWheelUp =
      key.upArrow ||
      key.pageUp ||
      char.includes('\x1b[<64') ||
      char.includes('\x1b[<0') ||
      char.includes('\x1b[M`') ||
      char.includes('\x1b[64');

    const isTouchpadOrWheelDown =
      key.downArrow ||
      key.pageDown ||
      char.includes('\x1b[<65') ||
      char.includes('\x1b[<1') ||
      char.includes('\x1b[Ma') ||
      char.includes('\x1b[65');

    if (isTouchpadOrWheelUp) {
      setScrollOffset(prev => Math.min(turns.length, prev + 1));
      return;
    }

    if (isTouchpadOrWheelDown) {
      setScrollOffset(prev => Math.max(0, prev - 1));
      return;
    }

    // Ctrl + S to save plan
    if ((key.ctrl || key.meta) && (char === 's' || char === 'S')) {
      const targetTurn = turns[turns.length - 1];
      const targetEvents = isRunning ? events : (targetTurn?.events || []);

      if (targetEvents.length > 0) {
        savePlanToFile(targetEvents, targetTurn?.prompt || 'Plan Request', process.cwd(), 'implementation-plan.md');

        setTurns(prev => {
          if (prev.length === 0) return prev;
          const lastIdx = prev.length - 1;
          const updatedEvents = prev[lastIdx].events.map(ev =>
            ev.kind === 'planner_action_panel' ? { ...ev, saved: true } : ev
          );
          return prev.map((t, i) => i === lastIdx ? { ...t, events: updatedEvents } : t);
        });
      }
      return;
    }

    if (overlay === 'mode') {
      if (key.escape) {
        setOverlay('none');
      }
      return;
    }

    if (isRunning && key.escape) {
      abort();
      setTurns(prev => {
        const last = prev[prev.length - 1];
        if (last && !last.isComplete) {
          return prev.map((t, i) => i === prev.length - 1 ? { ...t, isComplete: true } : t);
        }
        return prev;
      });
    }
  }, { isActive: true });

  useEffect(() => {
    if (!isRunning && events.length > 0 && activeTurn && !activeTurn.isComplete) {
      setTurns(prev => {
        const lastIdx = prev.length - 1;
        return prev.map((t, i) => i === lastIdx ? { ...t, events: [...events], isComplete: true } : t);
      });
    }
  }, [isRunning, events, activeTurn]);

  const handleSubmit = useCallback((value: string) => {
    const trimmed = value.trim();
    if (!trimmed) return;

    if (trimmed === '/mode') {
      setOverlay('mode');
      setInput('');
      setShowAutocomplete(false);
      return;
    }

    if (trimmed.startsWith('/')) {
      setInput('');
      setShowAutocomplete(false);
      return;
    }

    const turnId = `turn_${Date.now()}`;
    setTurns(prev => [...prev, {
      id: turnId,
      prompt: trimmed,
      mode: selectedMode,
      events: [],
      isComplete: false,
    }]);

    setInput('');
    setShowAutocomplete(false);
    startScenario(trimmed, selectedMode);
  }, [selectedMode, startScenario]);

  const handleAutocompleteSelect = useCallback((cmd: string) => {
    if (cmd === '/mode') {
      setOverlay('mode');
      setInput('');
      setShowAutocomplete(false);
    } else {
      setInput(cmd);
      setShowAutocomplete(false);
    }
  }, []);

  const handleModeSelect = useCallback((mode: ScenarioMode) => {
    setSelectedMode(mode);
    setOverlay('none');
  }, []);

  const renderPromptHeader = (prompt: string, mode: ScenarioMode) => (
    <Box flexDirection="row" marginBottom={1}>
      <Text color={theme.colors.text.muted}>{'> '}</Text>
      <Text color={theme.colors.text.ethereal} bold>{prompt}</Text>
      <Text color={theme.colors.text.muted}> </Text>
      <Text color={theme.colors.text.muted}>[{mode}]</Text>
    </Box>
  );

  return (
    <Box flexDirection="column" paddingX={1} paddingTop={1} width="100%">
      {/* Welcome Screen - always visible */}
      <WelcomeScreen persona={persona} mode={selectedMode} />

      {/* Conversation turns */}
      {turns.map((turn) => (
        <Box key={turn.id} flexDirection="column" marginTop={1}>
          {renderPromptHeader(turn.prompt, turn.mode)}
          {turn.events.length > 0 && (
            <ScenarioRenderer
              events={turn.events}
              isRunning={false}
              isHistorical={true}
            />
          )}
        </Box>
      ))}

      {/* Currently running scenario */}
      {isRunning && (
        <Box flexDirection="column" marginTop={1}>
          {activeTurn && renderPromptHeader(activeTurn.prompt, activeTurn.mode)}
          <ScenarioRenderer
            events={events}
            isRunning={isRunning}
            isHistorical={false}
          />
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
              <AutocompleteDropdown input={input} onSelect={handleAutocompleteSelect} />
            </Box>
          )}

          {/* File Picker Modal */}
          {showFilePicker && (
            <Box marginTop={1}>
              <FilePickerModal
                onSelectFile={(relPath) => {
                  setInput(prev => {
                    const cleaned = prev.replace(/^@/, '');
                    return cleaned ? `${cleaned} ${relPath}` : relPath;
                  });
                  setShowFilePicker(false);
                }}
                onClose={() => setShowFilePicker(false)}
              />
            </Box>
          )}

          {/* Claude Code CLI Session Status Bar */}
          {!showAutocomplete && !showFilePicker && (
            <SessionStatusBar
              mode={selectedMode}
              totalTokens={totalTokens}
              isRunning={isRunning}
            />
          )}
        </Box>
      )}

      {/* Mode select overlay */}
      {overlay === 'mode' && (
        <Box flexDirection="column" marginTop={1}>
          <ModeSelectScreen
            currentMode={selectedMode}
            onSelect={handleModeSelect}
            onClose={() => setOverlay('none')}
          />
        </Box>
      )}
    </Box>
  );
};
