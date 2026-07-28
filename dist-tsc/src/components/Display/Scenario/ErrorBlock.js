import { Box, Text } from 'ink';
import React from 'react';
import { useTheme } from '../../../theme/ThemeContext';
const _MAX_MESSAGE_LENGTH = 200;
export const ErrorBlock = React.memo(({ event, context }) => {
    const { theme } = useTheme();
    const displayMessage = event.message.trim();
    const badge = event.recoverable ? '[ERROR]' : '[FAILED]';
    return (React.createElement(Box, { flexDirection: "column", width: "100%", marginBottom: 1, paddingX: 1 },
        React.createElement(Box, { flexDirection: "column", width: "100%", borderStyle: "single", borderTop: false, borderRight: false, borderBottom: false, borderColor: theme.colors.status.error, paddingLeft: 1 },
            React.createElement(Box, { flexDirection: "row", alignItems: "flex-start", marginBottom: 0, flexWrap: "wrap" },
                React.createElement(Text, { color: theme.colors.status.error, bold: true },
                    badge,
                    ' '),
                React.createElement(Text, { color: theme.colors.text.bright, wrap: "wrap" }, displayMessage)),
            event.code && (React.createElement(Box, { flexDirection: "row", marginTop: 0 },
                React.createElement(Text, { color: theme.colors.text.muted }, "Code: "),
                React.createElement(Text, { color: theme.colors.status.warning }, event.code))),
            event.provider && (React.createElement(Box, { flexDirection: "row", marginTop: 0 },
                React.createElement(Text, { color: theme.colors.text.muted }, "Provider: "),
                React.createElement(Text, { color: theme.colors.text.bright }, event.provider))),
            React.createElement(Box, { flexDirection: "row", alignItems: "center", flexWrap: "wrap", marginTop: 0 },
                React.createElement(Text, { color: theme.colors.text.muted }, event.recoverable ? 'Recoverable' : 'Execution halted')),
            event.recoverable && (context?.onRetry || context?.onDismiss) && (React.createElement(Box, { flexDirection: "row", marginTop: 1, paddingX: 1 },
                context?.onRetry && (React.createElement(Box, { marginRight: 2 },
                    React.createElement(Text, { color: theme.colors.status.success, bold: true }, "[R] Retry"))),
                context?.onDismiss && (React.createElement(Box, null,
                    React.createElement(Text, { color: theme.colors.text.muted, bold: true }, "[D] Dismiss"))))))));
});
