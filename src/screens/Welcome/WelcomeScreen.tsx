import { Box, Text } from 'ink';
import React from 'react';
import { RoundedBox } from '../../components/ui/RoundedBox';
import { APP_VERSION } from '../../constants';
import { useProvider } from '../../hooks/useProvider';
import { getRecentSessions } from '../../services/data/SessionRepository';
import { useTheme } from '../../theme/ThemeContext';
import { getGreeting, WELCOME_DATA } from './data/welcomeData';

interface WelcomeScreenProps {
  workspace?: string;
}

export const WelcomeScreen: React.FC<WelcomeScreenProps> = React.memo(({ workspace }) => {
  const { theme } = useTheme();
  const { activeProvider } = useProvider();
  const activeWorkspace = workspace || process.cwd();
  const recentSessions = getRecentSessions();
  const activeModelDisplay = activeProvider.config.model || activeProvider.meta.defaultModel;

  return (
    <RoundedBox title={APP_VERSION} borderColor={theme.colors.border.active}>
      <Box
        flexGrow={1}
        width="100%"
        flexDirection="row"
        justifyContent="center"
        alignItems="center"
        paddingX={4}
        paddingY={2}
      >
        <Box flexDirection="column" width="60%" minWidth={56} paddingRight={2}>
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
                <Text color={theme.colors.text.muted}>Provider: </Text>
                <Text color={theme.colors.status.success} bold>
                  ✓ {activeProvider.meta.name}
                </Text>
                <Text color={theme.colors.text.muted}> | Model: </Text>
                <Text color={theme.colors.text.emerald} bold>
                  {activeModelDisplay}
                </Text>
              </Box>

              <Box flexDirection="row" marginTop={1}>
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

        <Box flexDirection="column" width="39%" justifyContent="center" paddingLeft={3}>
          <Box marginBottom={1} flexDirection="row" flexWrap="wrap">
            <Text color={theme.colors.text.emerald} bold>
              {getGreeting()}
            </Text>
          </Box>

          <Box flexDirection="column" width="100%" marginTop={1}>
            <Box flexDirection="row" alignItems="center" marginBottom={1}>
              <Text color={theme.colors.text.muted} bold>
                RECENT SESSIONS
              </Text>
            </Box>

            <Box flexDirection="column" width="100%">
              {recentSessions.length === 0 ? (
                <Text color={theme.colors.text.dim} italic>
                  No recent sessions
                </Text>
              ) : (
                recentSessions.map((session, idx) => {
                  const formattedTime = session.time.replace(/^\[\s*/, '').replace(/\s*\]$/, '');
                  return (
                    <Box key={idx} flexDirection="column" marginBottom={1} width="100%">
                      <Box flexDirection="row" alignItems="center">
                        <Text color={theme.colors.border.active}>│ </Text>
                        <Text color={theme.colors.text.ethereal} bold wrap="truncate-end">
                          {session.title}
                        </Text>
                      </Box>
                      <Box paddingLeft={2}>
                        <Text color={theme.colors.text.dim}>{formattedTime}</Text>
                      </Box>
                    </Box>
                  );
                })
              )}
            </Box>
          </Box>
        </Box>
      </Box>
    </RoundedBox>
  );
});
