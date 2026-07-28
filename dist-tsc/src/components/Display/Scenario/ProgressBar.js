import { Box, Text } from 'ink';
import React from 'react';
import { SPINNER_FRAMES } from '../../../constants/animation';
import { useTickAnimation } from '../../../hooks/useTickAnimation';
import { useTheme } from '../../../theme/ThemeContext';
export const ProgressBar = React.memo(({ event }) => {
    const { theme } = useTheme();
    const tick = useTickAnimation(200);
    const barWidth = 20;
    let progress;
    if (typeof event.percent === 'number') {
        progress = event.percent / 100;
    }
    else if (event.steps.length > 0) {
        const doneCount = event.steps.filter((s) => s.status === 'done').length;
        progress = doneCount / event.steps.length;
    }
    else {
        progress = 0;
    }
    const filled = Math.round(barWidth * progress);
    const activeIdx = event.steps.findIndex((s) => s.status === 'active');
    return (React.createElement(Box, { flexDirection: "column", width: "100%", marginBottom: 1, paddingX: 1 },
        React.createElement(Box, { flexDirection: "row", alignItems: "center", marginBottom: 1 },
            React.createElement(Text, { color: theme.colors.text.emerald, bold: true },
                "[",
                event.label,
                "]"),
            React.createElement(Text, { color: theme.colors.text.muted }, " "),
            React.createElement(Text, { color: theme.colors.status.success }, '\u2588'.repeat(filled)),
            React.createElement(Text, { color: theme.colors.text.muted }, '\u2591'.repeat(barWidth - filled)),
            React.createElement(Text, { color: theme.colors.text.muted }, " "),
            React.createElement(Text, { color: theme.colors.text.emerald, bold: true },
                Math.round(progress * 100),
                "%"),
            event.iteration !== undefined && (React.createElement(React.Fragment, null,
                React.createElement(Text, { color: theme.colors.text.muted }, " "),
                React.createElement(Text, { color: theme.colors.text.muted },
                    "(iter ",
                    event.iteration,
                    ")")))),
        event.steps.length > 0 && (React.createElement(Box, { flexDirection: "column", paddingLeft: 2 }, event.steps.map((step, idx) => {
            let icon;
            let color;
            switch (step.status) {
                case 'done':
                    icon = '✓';
                    color = theme.colors.text.emerald;
                    break;
                case 'active':
                    icon = SPINNER_FRAMES[tick % SPINNER_FRAMES.length];
                    color = theme.colors.text.ethereal;
                    break;
                case 'error':
                    icon = '✗';
                    color = theme.colors.text.error;
                    break;
                default:
                    icon = '○';
                    color = theme.colors.text.muted;
                    break;
            }
            return (React.createElement(Box, { key: idx, flexDirection: "row", alignItems: "center" },
                React.createElement(Box, { width: 2 },
                    React.createElement(Text, { color: color }, icon)),
                React.createElement(Text, { color: idx === activeIdx ? theme.colors.text.ethereal : theme.colors.text.muted }, step.label)));
        })))));
});
