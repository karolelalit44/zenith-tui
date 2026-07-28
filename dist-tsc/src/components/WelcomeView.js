import { Box, Text } from 'ink';
import React from 'react';
import { useTheme } from '../theme/ThemeContext';
const SUGGESTIONS = [
    'Help me understand this codebase',
    'Run the test suite and show results',
    'Create a new module with proper structure',
];
export const WelcomeView = ({ workspace }) => {
    const { theme } = useTheme();
    return (React.createElement(Box, { flexDirection: "column", paddingX: 1, paddingTop: 1, width: "100%" },
        React.createElement(Text, { color: theme.colors.text.muted, bold: true }, "Try asking:"),
        React.createElement(Box, { flexDirection: "column", marginTop: 1, paddingLeft: 1 }, SUGGESTIONS.map((suggestion, idx) => (React.createElement(Box, { key: idx, flexDirection: "row", marginBottom: 0 },
            React.createElement(Text, { color: theme.colors.status.accent },
                idx + 1,
                ". "),
            React.createElement(Text, { color: theme.colors.text.ethereal }, suggestion)))))));
};
