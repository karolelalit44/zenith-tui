import React, { useState, useEffect } from 'react';
import { Box, Text } from 'ink';
import { WelcomeScreen } from './screens/Welcome';
import { TreeLog } from './components/Display/TreeLog';
import { AddDirLog } from './components/Display/AddDirLog';
import { WordDiffViewer } from './components/Display/WordDiffViewer';
import { InputBox, OverlayState } from './components/Input/InputBox';
import { useTheme } from './theme/ThemeContext';
import { useMockEngine } from './hooks/useMockEngine';
import { LogItem, Persona } from './types';
import { SPINNER_FRAMES } from './constants';
import { CHAT_DATA } from './screens/Chat/data/chatData';

export const App: React.FC = () => {
  const { theme } = useTheme();
  const [input, setInput] = useState('');
  const [overlay, setOverlay] = useState<OverlayState>('none');
  const [persona, setPersona] = useState<Persona>('architect');
  const [autoApprove, setAutoApprove] = useState(true);
  const [spinnerTick, setSpinnerTick] = useState(0);

  const { history, isExecuting, loadingText, executeCommand } = useMockEngine();

  useEffect(() => {
    if (isExecuting) {
      const interval = setInterval(() => setSpinnerTick((s) => s + 1), 100);
      return () => clearInterval(interval);
    }
  }, [isExecuting]);

  return (
    <Box flexDirection="column" paddingX={1} paddingTop={1} width="100%">
      {history.length === 0 && <WelcomeScreen persona={persona} />}

      <Box flexDirection="column" marginTop={1} width="100%">
        {history.map((item: LogItem, idx: number) => {
          if (item.type === 'user') {
            return (
              <Box key={idx} flexDirection="row" marginBottom={1}>
                <Text color={theme.colors.text.muted}>{CHAT_DATA.userPrefix}</Text>
                <Text color={theme.colors.text.ethereal}>{item.text}</Text>
              </Box>
            );
          }
          if (item.type === 'text') {
            return (
              <Box key={idx} marginBottom={1}>
                <Text color={theme.colors.text.muted}>{CHAT_DATA.toolPrefix}</Text>
                <Text color={theme.colors.text.ethereal}>{item.text}</Text>
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
          if (item.type === 'add-dir') {
            return <AddDirLog key={idx} path={item.path} />;
          }
          return null;
        })}
      </Box>

      {isExecuting && (
        <Box marginBottom={1} flexDirection="row">
          <Box width={2}>
            <Text color={theme.colors.text.emerald}>
              {SPINNER_FRAMES[spinnerTick % 10]}
            </Text>
          </Box>
          <Text color={theme.colors.text.ethereal} bold>{loadingText}</Text>
          <Text color={theme.colors.text.muted}>{CHAT_DATA.loadingFooter.interruptHint}</Text>
        </Box>
      )}

      {!isExecuting ? (
        <InputBox
          input={input}
          setInput={setInput}
          overlay={overlay}
          setOverlay={setOverlay}
          isExecuting={isExecuting}
          executeCommand={executeCommand}
          persona={persona}
          setPersona={setPersona}
          autoApprove={autoApprove}
          setAutoApprove={setAutoApprove}
        />
      ) : null}

      {!isExecuting && (
        <Box marginTop={1}>
          <Text color={theme.colors.text.warning} bold>{CHAT_DATA.modeFooter.autoAcceptText}</Text>
          <Text color={theme.colors.text.muted}>{CHAT_DATA.modeFooter.cycleHint}</Text>
        </Box>
      )}
    </Box>
  );
};
