import { Box, Text } from 'ink';
import React, { useEffect, useState } from 'react';
import { ASCII_SPINNER_FRAMES } from '../../../constants/animation';
import { useTheme } from '../../../theme/ThemeContext';
import { TerminalMarkdown } from './TerminalMarkdown';
export const MessageBlock = React.memo(({ event }) => {
    const { theme } = useTheme();
    const [frameIdx, setFrameIdx] = useState(0);
    useEffect(() => {
        if (!event.partial)
            return;
        const id = setInterval(() => setFrameIdx((v) => (v + 1) % ASCII_SPINNER_FRAMES.length), 100);
        return () => clearInterval(id);
    }, [event.partial]);
    const hasContent = event.text && event.text.trim().length > 0;
    const icon = event.partial ? (React.createElement(Text, { color: theme.colors.status.accent },
        " ",
        ASCII_SPINNER_FRAMES[frameIdx % ASCII_SPINNER_FRAMES.length])) : null;
    return (React.createElement(Box, { flexDirection: "column", width: "100%", marginBottom: 1, paddingX: 1 },
        React.createElement(Box, { flexDirection: "row", alignItems: "center", marginBottom: hasContent ? 1 : 0 },
            React.createElement(Text, { color: theme.colors.status.accent, bold: true }, "\u25C7"),
            React.createElement(Text, { color: theme.colors.text.muted }, " Assistant"),
            icon),
        hasContent && (React.createElement(Box, { paddingLeft: 1, flexDirection: "column" },
            React.createElement(TerminalMarkdown, { content: event.text }))),
        !hasContent && !event.partial && (React.createElement(Box, { paddingLeft: 1, flexDirection: "column" },
            React.createElement(Text, { color: theme.colors.text.muted, italic: true }, "(empty response)")))));
});
