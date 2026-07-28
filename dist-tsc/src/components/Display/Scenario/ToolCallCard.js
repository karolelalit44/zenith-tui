import { Box, Text } from 'ink';
import React, { useEffect, useState } from 'react';
import { ASCII_SPINNER_FRAMES } from '../../../constants/animation';
import { useTheme } from '../../../theme/ThemeContext';
const SKIP_PARAMS = new Set([
    'content',
    'file_content',
    'old_content',
    'new_content',
    'data',
    'file_data',
    'filetext',
    'file_text',
    'source',
    'text',
    'body',
    'input',
    'output',
]);
function formatValue(val) {
    if (val === null || val === undefined)
        return 'null';
    if (typeof val === 'string') {
        if (val.length > 80)
            return `${val.slice(0, 77)}...`;
        return val;
    }
    if (typeof val === 'number' || typeof val === 'boolean')
        return String(val);
    const str = JSON.stringify(val);
    if (str.length > 80)
        return `${str.slice(0, 77)}...`;
    return str;
}
export const ToolCallCard = React.memo(({ event, context }) => {
    const { theme } = useTheme();
    const isPending = context?.isRunning && !context?.isHistorical;
    const [frameIdx, setFrameIdx] = useState(0);
    const [elapsed, setElapsed] = useState(0);
    useEffect(() => {
        if (!isPending)
            return;
        const id = setInterval(() => {
            setFrameIdx((v) => (v + 1) % ASCII_SPINNER_FRAMES.length);
            setElapsed((v) => v + 1);
        }, 100);
        return () => clearInterval(id);
    }, [isPending]);
    const params = event.params || {};
    const entries = Object.entries(params)
        .filter(([key]) => !SKIP_PARAMS.has(key.toLowerCase()))
        .slice(0, 5);
    return (React.createElement(Box, { flexDirection: "column", width: "100%", marginBottom: 1, paddingX: 1 },
        React.createElement(Box, { flexDirection: "row", alignItems: "center" },
            React.createElement(Text, { color: theme.colors.status.info, bold: true }, isPending ? React.createElement(React.Fragment, null,
                "[",
                ASCII_SPINNER_FRAMES[frameIdx % ASCII_SPINNER_FRAMES.length],
                " RUN] ") : React.createElement(React.Fragment, null,
                '>',
                " RUN ")),
            React.createElement(Text, { color: theme.colors.text.bright, bold: true }, event.tool),
            isPending && React.createElement(Text, { color: theme.colors.text.muted },
                " (",
                (elapsed / 10).toFixed(0),
                "s)")),
        entries.length > 0 && (React.createElement(Box, { flexDirection: "column", paddingLeft: 3 }, entries.map(([key, val]) => (React.createElement(Box, { key: key, flexDirection: "row" },
            React.createElement(Text, { color: theme.colors.text.muted },
                key,
                ": "),
            React.createElement(Text, { color: theme.colors.text.ethereal, wrap: "wrap" }, formatValue(val)))))))));
});
