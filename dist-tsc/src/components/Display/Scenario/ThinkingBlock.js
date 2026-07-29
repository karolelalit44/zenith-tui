import { Box, Text } from 'ink';
import React, { useEffect, useState } from 'react';
import { useTheme } from '../../../theme/ThemeContext';
const getThoughtText = (thought) => typeof thought === 'string' ? thought : thought.text;
const getThoughtDelay = (thought, index) => typeof thought === 'string' ? 0 : (thought.delay ?? index * 400);
function formatDuration(ms) {
    if (ms < 1000)
        return `${ms}ms`;
    const s = ms / 1000;
    if (s < 60)
        return `${s.toFixed(1)}s`;
    const m = Math.floor(s / 60);
    const rem = (s % 60).toFixed(0);
    return `${m}m ${rem}s`;
}
export const ThinkingBlock = React.memo(({ event, context }) => {
    const { theme } = useTheme();
    const isCollapsed = context?.thinkingCollapsed ?? true;
    const historical = context?.isHistorical ?? false;
    const [visibleCount, setVisibleCount] = useState(historical ? event.thoughts.length : 0);
    useEffect(() => {
        if (isCollapsed || historical) {
            setVisibleCount(event.thoughts.length);
            return;
        }
        const thoughts = event.thoughts;
        const timers = [];
        let cancelled = false;
        let cumulativeDelay = 0;
        thoughts.forEach((thought, idx) => {
            cumulativeDelay += Math.min(150, getThoughtDelay(thought, idx));
            const _revealTimer = setTimeout(() => {
                if (!cancelled)
                    setVisibleCount(idx + 1);
            }, cumulativeDelay);
            timers.push(_revealTimer);
        });
        return () => {
            cancelled = true;
            timers.forEach(clearTimeout);
        };
    }, [event.thoughts, isCollapsed, historical]);
    const displayedThoughts = isCollapsed || historical ? event.thoughts : event.thoughts.slice(0, visibleCount);
    return (React.createElement(Box, { flexDirection: "column", width: "100%", marginBottom: 1, paddingX: 1 },
        React.createElement(Box, { flexDirection: "row", alignItems: "center", marginBottom: isCollapsed ? 0 : 1, flexWrap: "wrap" },
            React.createElement(Text, { color: theme.colors.status.accent, bold: true }, isCollapsed ? '▶' : '▼'),
            React.createElement(Text, { color: theme.colors.text.muted },
                " ",
                event.thoughts.length,
                " thoughts"),
            event.duration > 0 && (React.createElement(React.Fragment, null,
                React.createElement(Text, { color: theme.colors.text.muted }, " \u00B7 "),
                React.createElement(Text, { color: theme.colors.text.muted }, formatDuration(event.duration)))),
            React.createElement(Text, { color: theme.colors.text.muted }, " \u00B7 "),
            React.createElement(Text, { color: theme.colors.text.bright, backgroundColor: theme.colors.bg.modal }, ' Ctrl+T '),
            React.createElement(Text, { color: theme.colors.text.dim }, " toggle")),
        !isCollapsed && (React.createElement(Box, { flexDirection: "column", paddingLeft: 2, width: "100%" }, displayedThoughts.map((thought, idx) => {
            const isLatest = !historical && idx === visibleCount - 1 && visibleCount < event.thoughts.length;
            return (React.createElement(Box, { key: idx, flexDirection: "row", alignItems: "flex-start", width: "100%", marginBottom: 0 },
                React.createElement(Box, { width: 2, flexShrink: 0 },
                    React.createElement(Text, { color: isLatest ? theme.colors.status.accent : theme.colors.text.muted }, isLatest ? '>' : '*')),
                React.createElement(Box, { flexShrink: 1 },
                    React.createElement(Text, { color: isLatest ? theme.colors.text.bright : theme.colors.text.muted, wrap: "wrap" }, getThoughtText(thought)))));
        })))));
});
