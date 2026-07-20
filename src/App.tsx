import React, { useState, useEffect } from 'react';
import { Box, Text, useInput } from 'ink';
import TextInput from 'ink-text-input';
import { DashboardScreen } from './screens/DashboardScreen';
import { TreeLog } from './components/TreeLog';
import { WordDiffViewer } from './components/WordDiffViewer';
import { PluginModal } from './components/PluginModal';
import { AutocompleteDropdown } from './components/AutocompleteDropdown';
import { theme } from './theme/theme';
import { useMockEngine, LogItem } from './hooks/useMockEngine';

type OverlayState = 'none' | 'autocomplete' | 'plugin';

export const App: React.FC = () => {
  const [input, setInput] = useState('');
  const [overlay, setOverlay] = useState<OverlayState>('none');
  const [spinnerTick, setSpinnerTick] = useState(0);
  
  const { history, isExecuting, loadingText, executeCommand } = useMockEngine();

  // Spinner animation
  useEffect(() => {
    if (isExecuting) {
      const interval = setInterval(() => setSpinnerTick((s) => s + 1), 100);
      return () => clearInterval(interval);
    }
  }, [isExecuting]);

  useInput((char, key) => {
    if (isExecuting) return;
    
    // Don't intercept chars if modal is open
    if (overlay === 'plugin') return;

    if (char === '/') {
      setOverlay('autocomplete');
    }
    
    if (key.escape && overlay === 'autocomplete') {
      setOverlay('none');
    }
  });

  const handleSubmit = (val: string) => {
    if (overlay === 'autocomplete') return;
    setOverlay('none');
    setInput('');
    executeCommand(val);
  };

  const handleAutocompleteSelect = (cmd: string) => {
    if (cmd === '/plugin') {
      setOverlay('plugin');
      setInput('');
    } else {
      setInput(cmd);
      setOverlay('none');
    }
  };

  const triggerPluginMock = () => {
    setOverlay('none');
    setInput('');
    executeCommand('/plugin');
  };

  return (
    <Box flexDirection="column" paddingX={1} paddingTop={1} width="100%">
      {/* 1. Scrolling History Stream */}
      {history.length === 0 && <DashboardScreen />}

      <Box flexDirection="column" marginTop={1} width="100%">
        {history.map((item, idx) => {
          if (item.type === 'user') {
             return (
               <Box key={idx} flexDirection="row" marginBottom={1}>
                 <Text color={theme.colors.text.muted}>{'> '}</Text>
                 <Text color={theme.colors.text.primary}>{item.text}</Text>
               </Box>
             );
          }
          if (item.type === 'text') {
             return (
               <Box key={idx} marginBottom={1}>
                 <Text color={theme.colors.text.muted}>● </Text>
                 <Text color={theme.colors.text.primary}>{item.text}</Text>
               </Box>
             );
          }
          if (item.type === 'tool') {
             return (
               <TreeLog key={idx} toolName={item.name} args={item.args} resultTitle={item.resultTitle}>
                 {item.diff && <WordDiffViewer lines={item.diff} />}
               </TreeLog>
             );
          }
          return null;
        })}
      </Box>

      {/* 2. Loading Footer */}
      {isExecuting && (
        <Box marginBottom={1}>
          <Text color={theme.colors.text.accentOrange}>
            {['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'][spinnerTick % 10]} {loadingText}
          </Text>
          <Text color={theme.colors.text.muted}> (esc to interrupt)</Text>
        </Box>
      )}

      {/* 3. The Input Layer */}
      {!isExecuting ? (
        <Box flexDirection="column" marginTop={1}>
          <Box flexDirection="row">
            <Text color={theme.colors.text.muted}>{'> '}</Text>
            <TextInput value={input} onChange={setInput} onSubmit={handleSubmit} focus={overlay !== 'plugin'} />
          </Box>
          
          {/* Overlays attach right under the input */}
          {overlay === 'autocomplete' && (
             <Box marginTop={1}><AutocompleteDropdown input={input} onSelect={handleAutocompleteSelect} /></Box>
          )}
          {overlay === 'plugin' && (
             <Box marginTop={1}><PluginModal onClose={() => setOverlay('none')} onTriggerMock={triggerPluginMock} /></Box>
          )}
        </Box>
      ) : null}

      {/* 4. Bottom Mode Footer */}
      {!isExecuting && (
        <Box marginTop={1}>
          <Text color={theme.colors.text.accentPurple} bold>▸▸ auto-accept edits on</Text>
          <Text color={theme.colors.text.muted}> (shift+tab to cycle)</Text>
        </Box>
      )}
    </Box>
  );
};
