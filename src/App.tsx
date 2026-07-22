import React, { useState } from 'react';
import { Box, Text } from 'ink';
import { WelcomeScreen } from './screens/Welcome';
import { OutputCard } from './components/Display/OutputCard';
import { InputBox, OverlayState } from './components/Input/InputBox';
import { ThinkingIndicator } from './components/Thinking';
import { useTheme } from './theme/ThemeContext';
import { useMockEngine } from './hooks/useMockEngine';
import { LogItem, Persona } from './types';
import { CHAT_DATA } from './screens/Chat/data/chatData';

export const App: React.FC = () => {
  const { theme } = useTheme();
  const [input, setInput] = useState('');
  const [overlay, setOverlay] = useState<OverlayState>('none');
  const [persona, setPersona] = useState<Persona>('architect');
  const [autoApprove, setAutoApprove] = useState(true);

  const { history, isExecuting, thinking, executeCommand } = useMockEngine();

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
          if (item.type === 'output') {
            return <OutputCard key={idx} meta={item.meta} />;
          }
          return null;
        })}
      </Box>

      {isExecuting && thinking.isActive && (
        <ThinkingIndicator
          phase={thinking.phase}
          message={thinking.message}
          steps={thinking.steps}
          currentStepIndex={thinking.currentStepIndex}
          showElapsed={true}
        />
      )}

      {isExecuting && !thinking.isActive && (
        <Box marginBottom={1} flexDirection="row">
          <Box width={2}>
            <Text color={theme.colors.text.emerald}>◈</Text>
          </Box>
          <Text color={theme.colors.text.ethereal} bold>Processing...</Text>
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
