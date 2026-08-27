import { Box, Text } from 'ink';
import React, { useEffect, useState } from 'react';
import { useTheme } from '../../theme/ThemeContext';

type ExitPhase = 'saving' | 'saved' | 'bye';

const PHASE_DURATION_MS = 500;

export const ExitScreen: React.FC = () => {
  const { theme } = useTheme();
  const [phase, setPhase] = useState<ExitPhase>('saving');
  const [dots, setDots] = useState('');

  useEffect(() => {
    if (phase !== 'saving') return;
    const id = setInterval(() => {
      setDots((d) => (d.length >= 3 ? '' : `${d}.`));
    }, 150);
    return () => clearInterval(id);
  }, [phase]);

  useEffect(() => {
    const t1 = setTimeout(() => setPhase('saved'), PHASE_DURATION_MS);
    const t2 = setTimeout(() => setPhase('bye'), PHASE_DURATION_MS * 2);
    const t3 = setTimeout(() => process.exit(0), PHASE_DURATION_MS * 3 + 200);
    return () => {
      clearTimeout(t1);
      clearTimeout(t2);
      clearTimeout(t3);
    };
  }, []);

  return (
    <Box
      flexDirection="column"
      width="100%"
      paddingX={2}
      paddingY={1}
      alignItems="flex-start"
      justifyContent="flex-start"
    >
      <Box flexDirection="row" alignItems="center">
        <Text color={phase === 'saving' ? theme.colors.status.warning : theme.colors.status.success}>
          {phase === 'saving' ? '○' : '■'}
        </Text>
        <Text color={theme.colors.text.muted}> </Text>
        <Text color={phase === 'saving' ? theme.colors.text.bright : theme.colors.text.muted}>
          Saving workspace{phase === 'saving' ? dots : ''}
        </Text>
      </Box>

      {(phase === 'saved' || phase === 'bye') && (
        <Box flexDirection="row" alignItems="center">
          <Text color={phase === 'bye' ? theme.colors.status.success : theme.colors.status.warning}>
            {phase === 'bye' ? '■' : '○'}
          </Text>
          <Text color={theme.colors.text.muted}> </Text>
          <Text color={phase === 'saved' ? theme.colors.text.bright : theme.colors.text.muted}>Session saved.</Text>
        </Box>
      )}

      {phase === 'bye' && (
        <Box flexDirection="row" alignItems="center" marginTop={1}>
          <Text color={theme.colors.status.success} bold>
            Goodbye 👋
          </Text>
        </Box>
      )}
    </Box>
  );
};
