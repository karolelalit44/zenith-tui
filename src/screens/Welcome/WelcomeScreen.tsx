import React from 'react';
import { Box, Text } from 'ink';
import { RoundedBox } from '../../components/ui/RoundedBox';
import { useTheme } from '../../theme/ThemeContext';
import { Persona } from '../../types';
import { WELCOME_DATA, getGreeting } from './data/welcomeData';
import { DEFAULT_WORKSPACE, ENGINE_MODEL, APP_VERSION } from '../../constants';

export const WelcomeScreen: React.FC<{ persona: Persona }> = React.memo(({ persona }) => {
  const { theme } = useTheme();

  return (
    <RoundedBox title={APP_VERSION} borderColor={theme.colors.border.active}>
      <Box flexGrow={1} width="100%" flexDirection="row" justifyContent="space-evenly" alignItems="center" paddingX={4} paddingY={2}>
        <Box flexDirection="column" width={56} flexShrink={0}>
          <Box marginBottom={1} flexDirection="column">
            <Text color={theme.colors.logo[0]} bold>███████╗ ███████╗ ███╗   ██╗ ██╗ ████████╗ ██╗  ██╗</Text>
            <Text color={theme.colors.logo[1]} bold>╚══███╔╝ ██╔════╝ ████╗  ██║ ██║ ╚══██╔══╝ ██║  ██║</Text>
            <Text color={theme.colors.logo[2]} bold>  ███╔╝  █████╗   ██╔██╗ ██║ ██║    ██║    ███████║</Text>
            <Text color={theme.colors.logo[3]} bold> ███╔╝   ██╔══╝   ██║╚██╗██║ ██║    ██║    ██╔══██║</Text>
            <Text color={theme.colors.logo[4]} bold>███████╗ ███████╗ ██║ ╚████║ ██║    ██║    ██║  ██║</Text>
            <Text color={theme.colors.logo[5]} bold>╚══════╝ ╚══════╝ ╚═╝  ╚═══╝ ╚═╝    ╚═╝    ╚═╝  ╚═╝</Text>
          </Box>

          <Box flexDirection="column" marginTop={1}>
            <Text color={theme.colors.text.ethereal} bold>{WELCOME_DATA.systemStatus.label}</Text>

            <Box flexDirection="row" marginTop={1}>
              <Box flexDirection="row" marginRight={4}>
                <Text color={theme.colors.text.muted}>{WELCOME_DATA.systemStatus.engineLabel}</Text>
                <Text color={theme.colors.text.emerald}>Online ({ENGINE_MODEL})</Text>
              </Box>
              <Box flexDirection="row">
                <Text color={theme.colors.text.muted}>{WELCOME_DATA.systemStatus.personaLabel}</Text>
                <Text color={theme.colors.text.warning}>{persona.charAt(0).toUpperCase() + persona.slice(1)} Mode</Text>
              </Box>
            </Box>

            <Box flexDirection="row" marginTop={1}>
              <Text color={theme.colors.text.muted}>{WELCOME_DATA.systemStatus.workspaceLabel}</Text>
              <Text color={theme.colors.text.emerald}>{DEFAULT_WORKSPACE}</Text>
            </Box>
          </Box>
        </Box>

        <Box width={1} justifyContent="center" alignItems="center">
          <Text color={theme.colors.border.muted}>║{"\n"}║{"\n"}║{"\n"}║{"\n"}║{"\n"}║{"\n"}║{"\n"}║{"\n"}║{"\n"}║{"\n"}║</Text>
        </Box>

        <Box flexDirection="column" width={56} justifyContent="center">
          <Box marginBottom={2} flexDirection="row" flexWrap="wrap">
            <Text color={theme.colors.text.emerald} bold>
              {getGreeting(persona)}
            </Text>
          </Box>

          <Text color={theme.colors.text.warning} bold>● Recent Sessions</Text>
          <Box marginTop={1} flexDirection="column">
            {WELCOME_DATA.recentSessions.map((session, idx) => (
              <Box key={idx} flexDirection="row" marginBottom={1}>
                <Box width={21}><Text color={theme.colors.text.muted}>{session.time} </Text></Box>
                <Box flexGrow={1} paddingRight={2}><Text color={theme.colors.text.ethereal} wrap="truncate-end">{session.title}</Text></Box>
                <Box width={12} flexDirection="row" justifyContent="flex-end">
                  <Text color={theme.colors.text.muted}>│ </Text>
                  <Text color={theme.colors.text.warning}>{session.persona}</Text>
                </Box>
              </Box>
            ))}
          </Box>
        </Box>
      </Box>
    </RoundedBox>
  );
});
