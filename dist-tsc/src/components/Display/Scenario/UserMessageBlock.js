import { Box, Text } from 'ink';
import React, { useEffect, useState } from 'react';
import { useTheme } from '../../../theme/ThemeContext';
export const UserMessageBlock = React.memo(({ prompt }) => {
    const { theme } = useTheme();
    const [columns, setColumns] = useState(() => process.stdout.columns ?? 80);
    useEffect(() => {
        const handleResize = () => {
            setColumns(process.stdout.columns ?? 80);
        };
        process.stdout.on('resize', handleResize);
        return () => {
            process.stdout.off('resize', handleResize);
        };
    }, []);
    const isCompact = columns < 75;
    const now = new Date();
    const timeStr = isCompact
        ? now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false })
        : `${now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false })}, ${now.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })}`;
    return (React.createElement(Box, { flexDirection: "column", width: "100%", marginBottom: 1 },
        React.createElement(Box, { flexDirection: "column", width: "100%", borderStyle: "round", borderColor: theme.colors.border.muted, paddingX: 1 },
            React.createElement(Box, { width: "100%" },
                React.createElement(Text, { color: theme.colors.text.bright, wrap: "wrap" }, prompt)),
            React.createElement(Box, { flexDirection: "row", justifyContent: "flex-end", width: "100%" },
                React.createElement(Text, { color: theme.colors.text.dim, wrap: "truncate-end" }, timeStr)))));
});
