import { Box, Text } from 'ink';
import React, { useEffect, useState } from 'react';
import { RoundedBox } from '../../components/ui/RoundedBox';
import { APP_VERSION } from '../../constants';
import { useProvider } from '../../hooks/useProvider';
import { useTerminalDimensions } from '../../hooks/useTerminalDimensions';
import type { SessionSummary } from '../../services/transport/WebSocketClient';
import { wsClient } from '../../services/transport/WebSocketClient';
import { useTheme } from '../../theme/ThemeContext';
import { sanitizeSingleLine } from '../../utils/text';
import { resolveWorkspaceRoot } from '../../utils/workspacePath';
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

function formatSessionTitle(title?: string): string {
  const firstLine = (title || '')
    .split(/\r?\n/)
    .map((line) => line.trim())
    .find(Boolean);
  return sanitizeSingleLine(firstLine || '') || 'Untitled Session';
}

const LOGO_LINES = [
  '███████╗ ███████╗ ███╗   ██╗ ██╗ ████████╗ ██╗  ██╗',
  '╚══███╔╝ ██╔════╝ ████╗  ██║ ██║ ╚══██╔══╝ ██║  ██║',
  '  ███╔╝  █████╗   ██╔██╗ ██║ ██║    ██║    ███████║',
  ' ███╔╝   ██╔══╝   ██║╚██╗██║ ██║    ██║    ██╔══██║',
  '███████╗ ███████╗ ██║ ╚████║ ██║    ██║    ██║  ██║',
  '╚══════╝ ╚══════╝ ╚═╝  ╚═══╝ ╚═╝    ╚═╝    ╚═╝  ╚═╝',
];

const LOGO_WIDTH = Math.max(...LOGO_LINES.map((line) => line.length));
const WELCOME_DESKTOP_MIN_COLUMNS = LOGO_WIDTH * 2 + 22;

export const WelcomeScreen: React.FC<WelcomeScreenProps> = React.memo(({ workspace }) => {
  const { theme } = useTheme();
  const { activeProvider } = useProvider();
  const { columns } = useTerminalDimensions();
  const termCols = columns || process.stdout.columns || 80;
  const compact = termCols < WELCOME_DESKTOP_MIN_COLUMNS;
  const activeWorkspace = workspace || resolveWorkspaceRoot();
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
    const title = formatSessionTitle(session.title);
    const meta = `${timeStr}${tokStr ? `  ${tokStr}` : ''}`;

    return (
      <Box
        key={session.id || idx}
        flexDirection={compact ? 'column' : 'row'}
        justifyContent="space-between"
        alignItems={compact ? 'flex-start' : 'center'}
        width="100%"
      >
        <Box flexShrink={1} width="100%" overflow="hidden">
          <Text color={theme.colors.text.bright} wrap="truncate-end">
            · {title}
          </Text>
        </Box>
        <Box flexShrink={compact ? 1 : 0} width={compact ? '100%' : undefined} marginLeft={compact ? 2 : 2}>
          <Text color={theme.colors.text.dim} wrap="truncate-end">
            {meta}
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
        flexDirection={compact ? 'column' : 'row'}
        justifyContent="space-between"
        alignItems={compact ? 'stretch' : 'center'}
        paddingX={compact ? 1 : 3}
        paddingY={compact ? 1 : 2}
      >
        <Box
          flexDirection="column"
          width={compact ? '100%' : '48%'}
          minWidth={compact ? undefined : LOGO_WIDTH}
          paddingRight={compact ? 0 : 2}
        >
          <Box marginBottom={1} flexDirection="column">
            {compact ? (
              <Text color={theme.colors.logo[0]} bold>
                ZENITH
              </Text>
            ) : (
              <>
                {LOGO_LINES.map((line, idx) => (
                  <Text key={line} color={theme.colors.logo[idx]} bold>
                    {line}
                  </Text>
                ))}
              </>
            )}
          </Box>

          <Box flexDirection="column" marginTop={1}>
            <Text color={theme.colors.text.ethereal} bold>
              {WELCOME_DATA.systemStatus.label}
            </Text>

            <Box flexDirection="column" marginTop={1}>
              <Box flexDirection="row" marginBottom={0}>
                <Text color={theme.colors.text.ethereal} wrap="truncate-end">
                  Provider: {activeProvider.meta.name} | Model: {activeModelDisplay}
                </Text>
              </Box>

              <Box flexDirection="row" marginTop={1}>
                <Box flexDirection="row">
                  <Text color={theme.colors.text.ethereal} wrap="truncate-end">
                    {WELCOME_DATA.systemStatus.workspaceLabel}
                    {activeWorkspace}
                  </Text>
                </Box>
              </Box>
            </Box>
          </Box>
        </Box>

        {!compact && (
          <Box width={1} justifyContent="center" alignItems="center">
            <Text color={theme.colors.border.muted}>
              │{'\n'}│{'\n'}│{'\n'}│{'\n'}│{'\n'}│{'\n'}│{'\n'}│{'\n'}│{'\n'}│{'\n'}│
            </Text>
          </Box>
        )}

        <Box
          flexDirection="column"
          width={compact ? '100%' : '48%'}
          justifyContent="center"
          paddingLeft={compact ? 0 : 2}
          marginTop={compact ? 1 : 0}
        >
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
