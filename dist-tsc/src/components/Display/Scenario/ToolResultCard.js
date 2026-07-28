import { Box, Text } from 'ink';
import React from 'react';
import { useTheme } from '../../../theme/ThemeContext';
function BashResult({ event, theme }) {
    const command = String(event.metadata.command || '');
    const outputLines = Array.isArray(event.metadata.output_lines)
        ? event.metadata.output_lines.map(String)
        : typeof event.metadata.output === 'string'
            ? event.metadata.output.split('\n')
            : [];
    const exitCode = typeof event.metadata.exit_code === 'number' ? event.metadata.exit_code : undefined;
    const duration = typeof event.metadata.duration_ms === 'number' ? event.metadata.duration_ms : undefined;
    const cleanedOutput = outputLines.map((l) => l.replace(/\r/g, '')).filter((l) => l.trim().length > 0);
    const width = Math.min(process.stdout.columns ?? 80, 80) - 4;
    return (React.createElement(Box, { flexDirection: "column", width: "100%", marginBottom: 1, paddingX: 1 },
        React.createElement(Box, { flexDirection: "row", alignItems: "center", marginBottom: 0 },
            React.createElement(Text, { color: event.success ? theme.colors.status.success : theme.colors.status.error, bold: true }, event.success ? '✓ [RUN]' : '✗ [RUN]'),
            React.createElement(Text, { color: theme.colors.text.muted }, " $ "),
            React.createElement(Text, { color: theme.colors.text.bright, bold: true }, command)),
        React.createElement(Box, { flexDirection: "column", width: "100%" },
            React.createElement(Box, { flexDirection: "row" },
                React.createElement(Text, { color: theme.colors.border.muted }, '┌─'),
                React.createElement(Text, { color: theme.colors.text.dim, bold: true }, ' terminal '),
                React.createElement(Text, { color: theme.colors.border.muted }, '─'.repeat(Math.max(0, width - 14))),
                React.createElement(Text, { color: theme.colors.border.muted }, '┐')),
            cleanedOutput.length > 0 ? (cleanedOutput.slice(0, 50).map((line, idx) => (React.createElement(Box, { key: idx, flexDirection: "row", width: "100%" },
                React.createElement(Text, { color: theme.colors.border.muted }, '│'),
                React.createElement(Text, { color: theme.colors.code.output, wrap: "wrap" },
                    ' ',
                    line))))) : (React.createElement(Box, { flexDirection: "row", width: "100%" },
                React.createElement(Text, { color: theme.colors.border.muted }, '│'),
                React.createElement(Text, { color: theme.colors.text.muted, italic: true }, '  (no output)'))),
            outputLines.length > 50 && (React.createElement(Box, { flexDirection: "row", width: "100%" },
                React.createElement(Text, { color: theme.colors.border.muted }, '│'),
                React.createElement(Text, { color: theme.colors.text.muted },
                    '  ... ',
                    outputLines.length - 50,
                    " more lines"))),
            React.createElement(Box, { flexDirection: "row", width: "100%" },
                React.createElement(Text, { color: theme.colors.border.muted }, '├─'),
                React.createElement(Text, { color: event.success ? theme.colors.status.success : theme.colors.status.error, bold: true }, ` exit ${exitCode ?? 0} `),
                duration !== undefined && React.createElement(Text, { color: theme.colors.text.dim },
                    (duration / 1000).toFixed(1),
                    "s"),
                React.createElement(Text, { color: theme.colors.border.muted }, '─'.repeat(Math.max(0, width - 20))),
                React.createElement(Text, { color: theme.colors.border.muted }, '┘')))));
}
function FileToolResult({ event, theme }) {
    const path = String(event.metadata.path || event.metadata.filepath || '');
    const fileName = path.split('/').pop() || path;
    return (React.createElement(Box, { flexDirection: "column", width: "100%", marginBottom: 1, paddingX: 1 },
        React.createElement(Box, { flexDirection: "row", alignItems: "center" },
            React.createElement(Text, { color: event.success ? theme.colors.status.success : theme.colors.status.error, bold: true },
                event.success ? '✓' : '✗',
                " [",
                event.tool.toUpperCase(),
                "]",
                ' '),
            React.createElement(Text, { color: theme.colors.text.bright }, fileName)),
        path && (React.createElement(Box, { paddingLeft: 3 },
            React.createElement(Text, { color: theme.colors.text.muted }, path)))));
}
function DefaultResult({ event, theme }) {
    const outputPreview = event.output ? event.output.split('\n').slice(0, 10).join('\n') : '';
    return (React.createElement(Box, { flexDirection: "column", width: "100%", marginBottom: 1, paddingX: 1 },
        React.createElement(Box, { flexDirection: "row", alignItems: "center" },
            React.createElement(Text, { color: event.success ? theme.colors.status.success : theme.colors.status.error, bold: true },
                event.success ? '✓' : '✗',
                " [",
                event.tool.toUpperCase(),
                "]",
                ' '),
            React.createElement(Text, { color: theme.colors.text.bright }, event.success ? 'Completed' : 'Failed'),
            event.error && React.createElement(Text, { color: theme.colors.status.error },
                " - ",
                event.error)),
        outputPreview && (React.createElement(Box, { paddingLeft: 3, marginTop: 0 },
            React.createElement(Text, { color: theme.colors.text.muted, wrap: "wrap" },
                outputPreview,
                event.output.split('\n').length > 10 && ' ...'))),
        event.truncated && (React.createElement(Box, { paddingLeft: 3 },
            React.createElement(Text, { color: theme.colors.text.muted, italic: true }, "(output truncated)")))));
}
export const ToolResultCard = React.memo(({ event }) => {
    const { theme } = useTheme();
    const tool = event.tool;
    if (tool === 'bash' || tool === 'execute' || tool === 'run_command') {
        return React.createElement(BashResult, { event: event, theme: theme });
    }
    if (tool === 'file_write' || tool === 'file_edit' || tool === 'file_delete') {
        return React.createElement(FileToolResult, { event: event, theme: theme });
    }
    if (tool === 'file_read') {
        const path = String(event.metadata.path || event.metadata.filepath || '');
        const fileName = path.split('/').pop() || path;
        const lines = event.output ? event.output.split('\n') : [];
        const preview = lines.slice(0, 30).join('\n');
        return (React.createElement(Box, { flexDirection: "column", width: "100%", marginBottom: 1, paddingX: 1 },
            React.createElement(Box, { flexDirection: "row", alignItems: "center" },
                React.createElement(Text, { color: theme.colors.status.success, bold: true },
                    "\u2713 [FILE_READ]",
                    ' '),
                React.createElement(Text, { color: theme.colors.text.bright }, fileName)),
            preview && (React.createElement(Box, { flexDirection: "column", width: "100%", borderStyle: "round", borderColor: theme.colors.text.muted, paddingX: 1, marginTop: 0 },
                lines.slice(0, 30).map((line, i) => (React.createElement(Text, { key: i, color: theme.colors.text.bright, wrap: "wrap" }, line))),
                lines.length > 30 && React.createElement(Text, { color: theme.colors.text.muted },
                    "... (",
                    lines.length - 30,
                    " more lines)")))));
    }
    return React.createElement(DefaultResult, { event: event, theme: theme });
});
