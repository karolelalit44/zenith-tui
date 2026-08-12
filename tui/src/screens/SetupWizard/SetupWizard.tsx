import { Box, Text, useInput } from 'ink';
import React, { useState } from 'react';
import { RoundedBox } from '../../components/ui/RoundedBox';
import { useTheme } from '../../theme/ThemeContext';
import type { AppStartupState } from '../../types/startup';
import { ProviderFlow } from '../Provider/ProviderFlow';

interface SetupWizardProps {
  startupState: AppStartupState;
  onComplete: () => void;
}

const MISSING_LABELS: Record<string, string> = {
  provider: 'AI Provider',
  model: 'Model Selection',
  apiKey: 'API Key',
  configFile: 'Configuration File',
  workspace: 'Workspace Directory',
  dbPath: 'Database Path',
};

export const SetupWizard: React.FC<SetupWizardProps> = ({ startupState, onComplete }) => {
  const { theme } = useTheme();
  const [started, setStarted] = useState(false);

  useInput((_char, key) => {
    if (started) return;
    if (key.escape) process.exit(0);
    if (key.return || _char === ' ') setStarted(true);
  });

  return (
    <RoundedBox title="ZENITH SETUP" borderColor={theme.colors.status.warning} hasShadow={true}>
      <Box flexDirection="column" paddingX={2} paddingY={1} width="100%">
        {!started && (
          <Box flexDirection="column" minHeight={6}>
            <Box marginBottom={1}>
              <Text color={theme.colors.status.warning} bold>
                ⚙ Setup Required
              </Text>
            </Box>
            <Text color={theme.colors.text.ethereal}>
              Before you can start using Zenith, an AI provider needs to be configured.
            </Text>
            {startupState.result?.missing?.length ? (
              <Box flexDirection="column" marginTop={1}>
                <Text color={theme.colors.status.warning} bold>
                  Missing Configuration:
                </Text>
                {startupState.result.missing.map((item) => (
                  <Box key={item} marginLeft={2}>
                    <Text color={theme.colors.status.error}>✗ </Text>
                    <Text color={theme.colors.text.ethereal}>{MISSING_LABELS[item] || item}</Text>
                  </Box>
                ))}
              </Box>
            ) : (
              startupState.error && (
                <Box marginTop={1}>
                  <Text color={theme.colors.status.error}>{startupState.error}</Text>
                </Box>
              )
            )}
            <Box marginTop={1}>
              <Text color={theme.colors.text.dim} italic>
                Press Enter to begin setup · Esc to exit
              </Text>
            </Box>
          </Box>
        )}
        {started && <ProviderFlow onClose={() => setStarted(false)} onComplete={onComplete} />}
      </Box>
    </RoundedBox>
  );
};
