import { Box, Text } from 'ink';
import React from 'react';
import { useTheme } from '../../../theme/ThemeContext';
export const ConfirmationCard = React.memo(({ event }) => {
    const { theme } = useTheme();
    const riskColor = event.riskLevel === 'high'
        ? theme.colors.status.error
        : event.riskLevel === 'medium'
            ? theme.colors.status.warning
            : theme.colors.status.success;
    const riskLabel = event.riskLevel === 'high' ? '[HIGH RISK]' : event.riskLevel === 'medium' ? '[MEDIUM RISK]' : '[LOW RISK]';
    return (React.createElement(Box, { flexDirection: "column", width: "100%", marginBottom: 1, paddingX: 1 },
        React.createElement(Box, { flexDirection: "column", width: "100%", borderStyle: "round", borderColor: riskColor, paddingX: 1, paddingY: 0 },
            React.createElement(Box, { flexDirection: "row", alignItems: "center" },
                React.createElement(Text, { color: riskColor, bold: true },
                    riskLabel,
                    ' '),
                React.createElement(Text, { color: theme.colors.text.bright },
                    "Confirm: ",
                    event.tool)),
            React.createElement(Box, { marginTop: 0 },
                React.createElement(Text, { color: theme.colors.text.muted }, event.reason)),
            event.answered ? (React.createElement(Box, { marginTop: 0 },
                React.createElement(Text, { color: event.approved ? theme.colors.status.success : theme.colors.status.error, bold: true }, event.approved ? '✓ Approved' : '✗ Denied'))) : (React.createElement(Box, { marginTop: 0 },
                React.createElement(Text, { color: theme.colors.text.bright },
                    "Press",
                    ' ',
                    React.createElement(Text, { color: theme.colors.status.success, bold: true }, "y"),
                    ' ',
                    "to approve or",
                    ' ',
                    React.createElement(Text, { color: theme.colors.status.error, bold: true }, "n"),
                    ' ',
                    "to deny"))))));
});
