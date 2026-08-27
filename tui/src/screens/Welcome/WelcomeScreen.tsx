import { Box, Text } from 'ink';
import React, { useEffect, useState } from 'react';
import { RoundedBox } from '../../components/ui/RoundedBox';
import { APP_VERSION } from '../../constants';
import { useProvider } from '../../hooks/useProvider';
import type { SessionSummary } from '../../services/transport/WebSocketClient';
import { wsClient } from '../../services/transport/WebSocketClient';
import { useTheme } from '../../theme/ThemeContext';
import { getGreeting, WELCOME_DATA } from './data/welcomeData';

interface WelcomeScreenProps {
  workspace?: string;
}

function formatSessionTime(isoStr: string): string {
  if (!isoStr) return '';
  try {
    const d = new Date(isoStr);
    const time = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: true });
    const date = d.toLocaleDateString([], { day: 'numeric', month: 'short', year: 'numeric' });
    return `${time} · ${date}`;
  } catch {
    return isoStr;
  }
}

function formatTokens(n: number): string {
  if (!n) return '';
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k tok`;
  return `${n} tok`;
}

export const WelcomeScreen: React.FC<WelcomeScreenProps> = React.memo(({ workspace }) => {
  const { theme } = useTheme();
  const { activeProvider } = useProvider();
  const activeWorkspace = workspace || process.cwd();
  const activeModelDisplay = activeProvider.config.model || activeProvider.meta.defaultModel;
  const [recentSessions, setRecentSessions] = useState<SessionSummary[]>([]);
  const [sessionsLoading, setSessionsLoading] = useState(true);
  const [sessionsError, setSessionsError] = useState(false);

  useEffect(() => {
    setSessionsLoading(true);
    setSessionsError(false);
    wsClient
      .listSessionSummaries({ limit: 5, include_archived: false })
      .then((sessions) => {
        setRecentSessions(sessions);
      })
      .catch((err) => {
        console.warn('Failed to load recent sessions:', err);
        setSessionsError(true);
        setRecentSessions([]);
      })
      .finally(() => setSessionsLoading(false));
  }, []);

  const renderSessionRow = (session: SessionSummary, idx: number) => {
    const timeStr = formatSessionTime(session.updated_at || session.created_at || '');
    const tokStr = formatTokens(session.total_tokens);
    const title = session.title?.trim() || 'Untitled Session';

    return (
      <Box key={session.id || idx} flexDirection="row" justifyContent="space-between" alignItems="center" width="100%">
        <Box flexShrink={1} overflow="hidden">
          <Text color={theme.colors.text.bright} wrap="truncate-end">
            · {title}
          </Text>
        </Box>
        <Box flexShrink={0} marginLeft={2}>
          <Text color={theme.colors.text.dim}>
            {timeStr}
            {tokStr ? `  ${tokStr}` : ''}
          </Text>
        </Box>
      </Box>
    );
  };

  return (
    <RoundedBox title={APP_VERSION} borderColor={theme.colors.border.active} hasShadow={true}>
      <Box
        flexGrow={1}
        width="100%"
        flexDirection="row"
        justifyContent="space-between"
        alignItems="center"
        paddingX={3}
        paddingY={2}
      >
        <Box flexDirection="column" width="48%" minWidth={48} paddingRight={2}>
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

        <Box flexDirection="column" width="48%" justifyContent="center" paddingLeft={2}>
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
              {sessionsLoading ? (
                <Text color={theme.colors.text.dim} italic>
                  Loading recent sessions...
                </Text>
              ) : sessionsError ? (
                <Text color={theme.colors.text.dim} italic>
                  Could not load recent sessions
                </Text>
              ) : recentSessions.length === 0 ? (
                <Text color={theme.colors.text.dim} italic>
                  No recent sessions
                </Text>
              ) : (
                recentSessions.map((session, idx) => renderSessionRow(session, idx))
              )}
            </Box>
          </Box>
        </Box>
      </Box>
    </RoundedBox>
  );
});
