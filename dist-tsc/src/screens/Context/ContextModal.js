import { Box, Text, useInput } from 'ink';
import React, { useMemo } from 'react';
import { ModalFooter } from '../../components/ui/ModalFooter';
import { RoundedBox } from '../../components/ui/RoundedBox';
import { estimateTokensForEvents, formatTokenCount } from '../../services/data/tokenEstimationService';
import { WORKSPACE_FILES } from '../../services/fileExplorerService';
import { useTheme } from '../../theme/ThemeContext';
export const ContextModal = ({ totalTokens, runningEvents = [], onClose }) => {
    const { theme } = useTheme();
    const liveTokens = useMemo(() => {
        return totalTokens + estimateTokensForEvents(runningEvents);
    }, [totalTokens, runningEvents]);
    useInput((_char, key) => {
        if (key.escape || key.return) {
            onClose();
        }
    });
    const contextPercent = Math.min(100, Math.round((liveTokens / 200000) * 100));
    const totalBlocks = 20;
    const filledBlocks = Math.max(0, Math.min(totalBlocks, Math.round((contextPercent / 100) * totalBlocks)));
    const bar = '█'.repeat(filledBlocks) + '░'.repeat(totalBlocks - filledBlocks);
    const sampleFiles = WORKSPACE_FILES.filter((f) => !f.isDir).slice(0, 7);
    const estimateFileTokens = (sizeFormatted) => {
        const sizeStr = sizeFormatted || '1.2 KB';
        const match = sizeStr.match(/([\d.]+)\s*(KB|MB|GB)/i);
        if (!match)
            return 300;
        const value = Number.parseFloat(match[1]);
        const unit = match[2].toUpperCase();
        let bytes = value * 1024;
        if (unit === 'MB')
            bytes = value * 1024 * 1024;
        if (unit === 'GB')
            bytes = value * 1024 * 1024 * 1024;
        return Math.round(bytes / 4);
    };
    return (React.createElement(RoundedBox, { title: "CONTEXT WINDOW INSPECTOR", borderColor: theme.colors.border.active, hasShadow: true },
        React.createElement(Box, { flexDirection: "column", paddingX: 2, paddingY: 1, width: "100%" },
            React.createElement(Box, { flexDirection: "row", alignItems: "center", marginBottom: 1 },
                React.createElement(Text, { color: theme.colors.text.emerald, bold: true },
                    "[CONTEXT USAGE]",
                    ' '),
                React.createElement(Text, { color: theme.colors.text.bright, bold: true },
                    formatTokenCount(liveTokens),
                    " (",
                    contextPercent,
                    "%)")),
            React.createElement(Box, { flexDirection: "row", alignItems: "center", marginBottom: 1 },
                React.createElement(Text, { color: theme.colors.status.success },
                    "[",
                    bar,
                    "]")),
            React.createElement(Box, { flexDirection: "row", marginBottom: 1, borderStyle: "single", borderTop: true, borderBottom: true, borderLeft: false, borderRight: false, borderColor: theme.colors.border.muted },
                React.createElement(Box, { width: 32 },
                    React.createElement(Text, { color: theme.colors.text.muted, bold: true }, "ACTIVE FILE / RESOURCE")),
                React.createElement(Box, { width: 16 },
                    React.createElement(Text, { color: theme.colors.text.muted, bold: true }, "SIZE")),
                React.createElement(Box, { width: 16 },
                    React.createElement(Text, { color: theme.colors.text.muted, bold: true }, "EST. TOKENS"))),
            sampleFiles.length === 0 ? (React.createElement(Box, { paddingY: 1 },
                React.createElement(Text, { color: theme.colors.text.dim, italic: true }, "No workspace files loaded."))) : (sampleFiles.map((f, idx) => {
                const fileTokens = estimateFileTokens(f.sizeFormatted);
                return (React.createElement(Box, { key: idx, flexDirection: "row", alignItems: "center", width: "100%" },
                    React.createElement(Box, { width: 32 },
                        React.createElement(Text, { color: theme.colors.text.dim, wrap: "truncate-end" }, f.relativePath)),
                    React.createElement(Box, { width: 16 },
                        React.createElement(Text, { color: theme.colors.text.dim }, f.sizeFormatted || '1.2 KB')),
                    React.createElement(Box, { width: 16 },
                        React.createElement(Text, { color: theme.colors.text.dim }, formatTokenCount(fileTokens)))));
            })),
            React.createElement(Box, { marginTop: 1, paddingTop: 1, borderStyle: "single", borderTop: true, borderBottom: false, borderLeft: false, borderRight: false, borderColor: theme.colors.border.muted },
                React.createElement(Text, { color: theme.colors.text.muted },
                    React.createElement(ModalFooter, { shortcuts: [{ key: '[Esc]', label: 'to exit Context Window' }] }))))));
};
