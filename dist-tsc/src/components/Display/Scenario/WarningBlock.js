import { Box, Text } from 'ink';
import React from 'react';
import { useTheme } from '../../../theme/ThemeContext';
export const WarningBlock = React.memo(({ event }) => {
    const { theme } = useTheme();
    return (React.createElement(Box, { flexDirection: "column", width: "100%", marginBottom: 1, paddingX: 1 },
        React.createElement(Box, { flexDirection: "column", width: "100%", borderStyle: "round", borderColor: theme.colors.status.warning, paddingX: 1, paddingY: 1 },
            React.createElement(Box, { flexDirection: "row", alignItems: "center", marginBottom: 1, flexWrap: "wrap" },
                React.createElement(Text, { color: theme.colors.status.warning, bold: true },
                    "[WARNING]",
                    ' '),
                React.createElement(Text, { color: theme.colors.text.bright, bold: true }, event.message)),
            event.code && (React.createElement(Box, { marginTop: 0, paddingLeft: 1 },
                React.createElement(Text, { color: theme.colors.text.muted },
                    "Code: ",
                    event.code))),
            React.createElement(Box, { marginTop: 1, flexDirection: "row", justifyContent: "flex-end" },
                React.createElement(Text, { color: theme.colors.text.dim }, "[NON-FATAL - Execution Continuing]")))));
});
