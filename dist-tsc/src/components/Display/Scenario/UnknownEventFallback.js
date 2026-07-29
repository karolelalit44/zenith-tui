import { Box, Text } from 'ink';
import React from 'react';
import { useTheme } from '../../../theme/ThemeContext';
export const UnknownEventFallback = React.memo(({ event }) => {
    const { theme } = useTheme();
    const eventKind = event.kind ? String(event.kind).toUpperCase() : 'EVENT';
    return (React.createElement(Box, { flexDirection: "column", width: "100%", marginBottom: 1, paddingX: 1 },
        React.createElement(Box, { flexDirection: "row", alignItems: "center", marginBottom: 1 },
            React.createElement(Text, { color: theme.colors.status.warning, bold: true },
                "[",
                eventKind,
                "]"),
            React.createElement(Text, { color: theme.colors.text.muted }, " "),
            React.createElement(Text, { color: theme.colors.text.bright }, "Generic Event Payload")),
        React.createElement(Box, { flexDirection: "column", width: "100%", borderStyle: "round", borderColor: theme.colors.status.warning, paddingX: 2, paddingY: 1 },
            React.createElement(Box, { marginBottom: 1 },
                React.createElement(Text, { color: theme.colors.text.muted, italic: true },
                    "No specific UI renderer registered for kind: \"",
                    event.kind,
                    "\". Fallback raw data render:")),
            Object.entries(event)
                .filter(([key]) => key !== 'id' && key !== 'kind')
                .map(([key, val], idx) => (React.createElement(Box, { key: idx, flexDirection: "row", marginBottom: 0 },
                React.createElement(Text, { color: theme.colors.status.info, bold: true },
                    key,
                    ":",
                    ' '),
                React.createElement(Text, { color: theme.colors.text.ethereal }, typeof val === 'object' ? JSON.stringify(val) : String(val))))))));
});
