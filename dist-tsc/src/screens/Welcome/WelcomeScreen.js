import { Box, Text } from 'ink';
import React from 'react';
import { RoundedBox } from '../../components/ui/RoundedBox';
import { APP_VERSION } from '../../constants';
import { useProvider } from '../../hooks/useProvider';
import { getRecentSessions } from '../../services/data/SessionRepository';
import { useTheme } from '../../theme/ThemeContext';
import { getGreeting, WELCOME_DATA } from './data/welcomeData';
export const WelcomeScreen = React.memo(({ workspace }) => {
    const { theme } = useTheme();
    const { activeProvider } = useProvider();
    const activeWorkspace = workspace || process.cwd();
    const recentSessions = getRecentSessions();
    const activeModelDisplay = activeProvider.config.model || activeProvider.meta.defaultModel;
    return (React.createElement(RoundedBox, { title: APP_VERSION, borderColor: theme.colors.border.active, hasShadow: true },
        React.createElement(Box, { flexGrow: 1, width: "100%", flexDirection: "row", justifyContent: "center", alignItems: "center", paddingX: 4, paddingY: 2 },
            React.createElement(Box, { flexDirection: "column", width: "60%", minWidth: 56, paddingRight: 2 },
                React.createElement(Box, { marginBottom: 1, flexDirection: "column" },
                    React.createElement(Text, { color: theme.colors.logo[0], bold: true }, '███████╗ ███████╗ ███╗   ██╗ ██╗ ████████╗ ██╗  ██╗'),
                    React.createElement(Text, { color: theme.colors.logo[1], bold: true }, '╚══███╔╝ ██╔════╝ ████╗  ██║ ██║ ╚══██╔══╝ ██║  ██║'),
                    React.createElement(Text, { color: theme.colors.logo[2], bold: true }, '  ███╔╝  █████╗   ██╔██╗ ██║ ██║    ██║    ███████║'),
                    React.createElement(Text, { color: theme.colors.logo[3], bold: true }, ' ███╔╝   ██╔══╝   ██║╚██╗██║ ██║    ██║    ██╔══██║'),
                    React.createElement(Text, { color: theme.colors.logo[4], bold: true }, '███████╗ ███████╗ ██║ ╚████║ ██║    ██║    ██║  ██║'),
                    React.createElement(Text, { color: theme.colors.logo[5], bold: true }, '╚══════╝ ╚══════╝ ╚═╝  ╚═══╝ ╚═╝    ╚═╝    ╚═╝  ╚═╝')),
                React.createElement(Box, { flexDirection: "column", marginTop: 1 },
                    React.createElement(Text, { color: theme.colors.text.ethereal, bold: true }, WELCOME_DATA.systemStatus.label),
                    React.createElement(Box, { flexDirection: "column", marginTop: 1 },
                        React.createElement(Box, { flexDirection: "row", marginBottom: 0 },
                            React.createElement(Text, { color: theme.colors.text.muted }, "Provider: "),
                            React.createElement(Text, { color: theme.colors.status.success, bold: true },
                                "\u2713 ",
                                activeProvider.meta.name),
                            React.createElement(Text, { color: theme.colors.text.muted }, " | Model: "),
                            React.createElement(Text, { color: theme.colors.text.emerald, bold: true }, activeModelDisplay)),
                        React.createElement(Box, { flexDirection: "row", marginTop: 1 },
                            React.createElement(Box, { flexDirection: "row" },
                                React.createElement(Text, { color: theme.colors.text.muted }, WELCOME_DATA.systemStatus.workspaceLabel),
                                React.createElement(Text, { color: theme.colors.text.emerald }, activeWorkspace)))))),
            React.createElement(Box, { width: 1, justifyContent: "center", alignItems: "center" },
                React.createElement(Text, { color: theme.colors.border.muted },
                    "\u2502",
                    '\n',
                    "\u2502",
                    '\n',
                    "\u2502",
                    '\n',
                    "\u2502",
                    '\n',
                    "\u2502",
                    '\n',
                    "\u2502",
                    '\n',
                    "\u2502",
                    '\n',
                    "\u2502",
                    '\n',
                    "\u2502",
                    '\n',
                    "\u2502",
                    '\n',
                    "\u2502")),
            React.createElement(Box, { flexDirection: "column", width: "39%", justifyContent: "center", paddingLeft: 3 },
                React.createElement(Box, { marginBottom: 1, flexDirection: "row", flexWrap: "wrap" },
                    React.createElement(Text, { color: theme.colors.text.emerald, bold: true }, getGreeting())),
                React.createElement(Box, { flexDirection: "column", width: "100%", marginTop: 1 },
                    React.createElement(Box, { flexDirection: "row", alignItems: "center", marginBottom: 1 },
                        React.createElement(Text, { color: theme.colors.text.muted, bold: true }, "RECENT SESSIONS")),
                    React.createElement(Box, { flexDirection: "column", width: "100%" }, recentSessions.length === 0 ? (React.createElement(Text, { color: theme.colors.text.dim, italic: true }, "No recent sessions")) : (recentSessions.map((session, idx) => {
                        const formattedTime = session.time.replace(/^\[\s*/, '').replace(/\s*\]$/, '');
                        return (React.createElement(Box, { key: idx, flexDirection: "column", marginBottom: 1, width: "100%" },
                            React.createElement(Box, { flexDirection: "row", alignItems: "center" },
                                React.createElement(Text, { color: theme.colors.border.active }, "\u2502 "),
                                React.createElement(Text, { color: theme.colors.text.ethereal, bold: true, wrap: "truncate-end" }, session.title)),
                            React.createElement(Box, { paddingLeft: 2 },
                                React.createElement(Text, { color: theme.colors.text.dim }, formattedTime))));
                    }))))))));
});
