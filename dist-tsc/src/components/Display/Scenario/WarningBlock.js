import { Box, Text } from 'ink';
import React from 'react';
import { useTheme } from '../../../theme/ThemeContext';
export const WarningBlock = React.memo(({ event }) => {
    const { theme } = useTheme();
    return (React.createElement(Box, { flexDirection: "row", width: "100%", marginBottom: 1, paddingX: 1, alignItems: "center" },
        React.createElement(Text, { color: theme.colors.status.warning, bold: true },
            "\u25B2 [WARNING]",
            ' '),
        React.createElement(Text, { color: theme.colors.text.bright, wrap: "wrap" }, event.message),
        event.code && React.createElement(Text, { color: theme.colors.text.dim },
            " (",
            event.code,
            ")")));
});
