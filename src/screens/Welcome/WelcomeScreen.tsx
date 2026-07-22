import { Box, Text } from 'ink';
import React from 'react';
import { RoundedBox } from '../../components/ui/RoundedBox';
import { APP_VERSION, DEFAULT_WORKSPACE } from '../../constants';
import { useProvider } from '../../hooks/useProvider';
import { getRecentSessions } from '../../services/data/SessionRepository';
import { useTheme } from '../../theme/ThemeContext';
import type { Persona } from '../../types';
import type { ScenarioMode } from '../../types/scenario';
import { getGreeting, WELCOME_DATA } from './data/welcomeData';

interface WelcomeScreenProps {
  persona: Persona;
  mode: ScenarioMode;
  workspace?: string;
}

export const WelcomeScreen: React.FC<WelcomeScreenProps> = React.memo(({ persona, mode, workspace }) => {
  const { theme } = useTheme();
  const { activeProvider } = useProvider();
  const activeWorkspace = workspace || DEFAULT_WORKSPACE;
  const recentSessions = getRecentSessions();
  const activeModelDisplay = activeProvider.config.model || activeProvider.meta.defaultModel;

  return (
    <RoundedBox title={APP_VERSION} borderColor={theme.colors.border.active}>
      <Box
        flexGrow={1}
        width="100%"
        flexDirection="row"
        justifyContent="space-evenly"
        alignItems="center"
        paddingX={4}
        paddingY={2}
      >
        <Box flexDirection="column" width={56} flexShrink={0}>
          <Box marginBottom={1} flexDirection="column">
            <Text color={theme.colors.logo[0]} bold>
              {'███████╗ ███████╗ ███╗   ██╗ ██╗ ████████╗ ██╗  ██╗'}
            </Text>
            <Text color={theme.colors.logo[1]} bold>
              {'╚══███╔╝ ██╔════╝ ████╗  ██║ ██║ ╚══██╔══╝ ██║  ██║'}
            </Text>
            <Text color={theme.colors.logo[2]} bold>
              {'  ███╔╝  █████╗   ██╔██╗ ██║ ██║    ██║    ███████║'}
            </Text>
            <Text color={theme.colors.logo[3]} bold>
              {' ███╔╝   ██╔══╝   ██║╚██╗██║ ██║    ██║    ██╔══██║'}
            </Text>
            <Text color={theme.colors.logo[4]} bold>
              {'███████╗ ███████╗ ██║ ╚████║ ██║    ██║    ██║  ██║'}
            </Text>
            <Text color={theme.colors.logo[5]} bold>
              {'╚══════╝ ╚══════╝ ╚═╝  ╚═══╝ ╚═╝    ╚═╝    ╚═╝  ╚═╝'}
            </Text>
          </Box>

          <Box flexDirection="column" marginTop={1}>
            <Text color={theme.colors.text.ethereal} bold>
              {WELCOME_DATA.systemStatus.label}
            </Text>

            <Box flexDirection="column" marginTop={1}>
              <Box flexDirection="row" marginBottom={0}>
                <Text color={theme.colors.text.muted}>Connected Provider: </Text>
                <Text color={theme.colors.status.success} bold>
                  ✓ {activeProvider.meta.name}
                </Text>
                <Text color={theme.colors.text.muted}> | Model: </Text>
                <Text color={theme.colors.text.emerald} bold>
                  {activeModelDisplay}
                </Text>
              </Box>

              <Box flexDirection="row" marginTop={1}>
                <Box flexDirection="row" marginRight={4}>
                  <Text color={theme.colors.text.muted}>Mode: </Text>
                  <Text color={theme.colors.text.emerald} bold>
                    {mode.charAt(0).toUpperCase() + mode.slice(1)}
                  </Text>
                </Box>

                <Box flexDirection="row">
                  <Text color={theme.colors.text.muted}>{WELCOME_DATA.systemStatus.workspaceLabel}</Text>
                  <Text color={theme.colors.text.emerald}>{activeWorkspace}</Text>
                </Box>
              </Box>
            </Box>
          </Box>
        </Box>

        <Box width={1} justifyContent="center" alignItems="center">
          <Text color={theme.colors.border.muted}>
            │{'\n'}│{'\n'}│{'\n'}│{'\n'}│{'\n'}│{'\n'}│{'\n'}│{'\n'}│{'\n'}│{'\n'}│
          </Text>
        </Box>

        <Box flexDirection="column" flexGrow={1} flexShrink={1} justifyContent="center" paddingLeft={2}>
          <Box marginBottom={2} flexDirection="row" flexWrap="wrap">
            <Text color={theme.colors.text.emerald} bold>
              {getGreeting(persona)}
            </Text>
          </Box>

          <Text color={theme.colors.text.warning} bold>
            Recent Sessions
          </Text>
          <Box marginTop={1} flexDirection="column" width="100%">
            {recentSessions.map((session, idx) => (
              <Box key={idx} flexDirection="row" marginBottom={1} width="100%">
                <Box width={18} flexShrink={0}>
                  <Text color={theme.colors.text.muted}>{session.time} </Text>
                </Box>
                <Box flexGrow={1} flexShrink={1} paddingRight={1}>
                  <Text color={theme.colors.text.ethereal} wrap="truncate-end">
                    {session.title}
                  </Text>
                </Box>
                <Box width={12} flexShrink={0} flexDirection="row" justifyContent="flex-end">
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
