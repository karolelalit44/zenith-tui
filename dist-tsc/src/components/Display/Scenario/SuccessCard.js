import { Box, Text } from 'ink';
import React from 'react';
import { formatTokenCount } from '../../../services/data/tokenEstimationService';
import { useTheme } from '../../../theme/ThemeContext';
export const SuccessCard = React.memo(({ event }) => {
    const { theme } = useTheme();
    const parts = [];
    if (event.iterations !== undefined) {
        parts.push(`${event.iterations} iter${event.iterations === 1 ? '' : 's'}`);
    }
    if (event.tokenInfo) {
        parts.push(`${formatTokenCount(event.tokenInfo.used)} tokens`);
    }
    return (React.createElement(Box, { flexDirection: "column", width: "100%", paddingX: 1, marginBottom: 1 },
        React.createElement(Box, { flexDirection: "row", alignItems: "center" },
            React.createElement(Text, { color: theme.colors.status.success }, "\u2713 "),
            parts.length > 0 ? (React.createElement(Text, { color: theme.colors.text.muted }, parts.join(' · '))) : (React.createElement(Text, { color: theme.colors.text.muted }, "done")))));
});
