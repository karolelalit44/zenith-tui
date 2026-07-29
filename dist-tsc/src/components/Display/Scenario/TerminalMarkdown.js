import { Box, Text } from 'ink';
import React from 'react';
import { useTheme } from '../../../theme/ThemeContext';
import { highlightCode } from '../../../utils/syntaxHighlight';
function parseInlineTokens(text) {
    const tokens = [];
    const regex = /(\*\*.*?\*\*|\*.*?\*|`.*?`)/g;
    let lastIdx = 0;
    let match = regex.exec(text);
    while (match !== null) {
        if (match.index > lastIdx) {
            tokens.push({ text: text.slice(lastIdx, match.index) });
        }
        const matched = match[0];
        if (matched.startsWith('**') && matched.endsWith('**')) {
            tokens.push({ text: matched.slice(2, -2), bold: true });
        }
        else if (matched.startsWith('*') && matched.endsWith('*')) {
            tokens.push({ text: matched.slice(1, -1), italic: true });
        }
        else if (matched.startsWith('`') && matched.endsWith('`')) {
            tokens.push({ text: matched.slice(1, -1), code: true });
        }
        lastIdx = regex.lastIndex;
        match = regex.exec(text);
    }
    if (lastIdx < text.length) {
        tokens.push({ text: text.slice(lastIdx) });
    }
    return tokens;
}
const FormattedInlineText = ({ text }) => {
    const { theme } = useTheme();
    const tokens = parseInlineTokens(text);
    return (React.createElement(Text, null, tokens.map((t, i) => {
        if (t.code) {
            return (React.createElement(Text, { key: i, color: theme.colors.status.warning, backgroundColor: theme.colors.bg.modal }, ` ${t.text} `));
        }
        if (t.bold) {
            return (React.createElement(Text, { key: i, color: theme.colors.text.bright, bold: true }, t.text));
        }
        if (t.italic) {
            return (React.createElement(Text, { key: i, color: theme.colors.text.ethereal, italic: true }, t.text));
        }
        return (React.createElement(Text, { key: i, color: theme.colors.text.ethereal }, t.text));
    })));
};
function parseTable(lines) {
    if (lines.length < 2)
        return null;
    const parseRow = (line) => line
        .trim()
        .slice(1, -1)
        .split('|')
        .map((c) => c.trim());
    const headers = parseRow(lines[0]);
    if (!lines[1].includes('---'))
        return null;
    const rows = [];
    for (let i = 2; i < lines.length; i++) {
        if (lines[i].includes('|')) {
            rows.push(parseRow(lines[i]));
        }
    }
    return { headers, rows };
}
const MarkdownTableRenderer = ({ table }) => {
    const { theme } = useTheme();
    const colWidths = table.headers.map((h, i) => {
        let max = h.length;
        table.rows.forEach((r) => {
            if (r[i] && r[i].length > max) {
                max = r[i].length;
            }
        });
        return Math.max(max, 6);
    });
    const makeRowStr = (cells) => `│ ${cells.map((cell, i) => (cell || '').padEnd(colWidths[i])).join(' │ ')} │`;
    const topBorder = `┌─${colWidths.map((w) => '─'.repeat(w)).join('─┬─')}─┐`;
    const headerSep = `├─${colWidths.map((w) => '─'.repeat(w)).join('─┼─')}─┤`;
    const bottomBorder = `└─${colWidths.map((w) => '─'.repeat(w)).join('─┴─')}─┘`;
    return (React.createElement(Box, { flexDirection: "column", marginY: 1 },
        React.createElement(Text, { color: theme.colors.border.muted }, topBorder),
        React.createElement(Box, { flexDirection: "row" },
            React.createElement(Text, { color: theme.colors.text.bright, bold: true }, makeRowStr(table.headers))),
        React.createElement(Text, { color: theme.colors.border.muted }, headerSep),
        table.rows.map((r, idx) => (React.createElement(Box, { key: idx, flexDirection: "row" },
            React.createElement(Text, { color: theme.colors.text.ethereal }, makeRowStr(r))))),
        React.createElement(Text, { color: theme.colors.border.muted }, bottomBorder)));
};
export const TerminalMarkdown = ({ content }) => {
    const { theme } = useTheme();
    if (!content)
        return null;
    const rawLines = content.split('\n');
    const blocks = [];
    let idx = 0;
    while (idx < rawLines.length) {
        const line = rawLines[idx];
        // Intercept raw tool call dumps like [file_write path="..." content="..."]
        const fileWriteMatch = line.trim().match(/^\[file_write\s+path=["']([^"']+)["']\s+content=["']([\s\S]*)["']\]?$/);
        if (fileWriteMatch) {
            const filePath = fileWriteMatch[1];
            const rawContent = fileWriteMatch[2].replace(/\\n/g, '\n').replace(/\\"/g, '"');
            const ext = filePath.split('.').pop() || 'text';
            const fileCodeLines = rawContent.split('\n');
            const MAX_CODE_LINES = 15;
            const isTruncated = fileCodeLines.length > MAX_CODE_LINES;
            const visibleLines = isTruncated ? fileCodeLines.slice(0, MAX_CODE_LINES) : fileCodeLines;
            blocks.push(React.createElement(Box, { key: `filewrite_${idx}`, flexDirection: "column", marginY: 1, width: "100%" },
                React.createElement(Box, { flexDirection: "row", justifyContent: "space-between", paddingX: 1, backgroundColor: theme.colors.bg.modal },
                    React.createElement(Text, { color: theme.colors.status.success, bold: true },
                        "\u2713 [FILE_WRITE] ",
                        filePath),
                    React.createElement(Text, { color: theme.colors.text.muted },
                        fileCodeLines.length,
                        " ",
                        fileCodeLines.length === 1 ? 'line' : 'lines')),
                React.createElement(Box, { flexDirection: "column", paddingX: 1, paddingY: 0, borderStyle: "round", borderColor: theme.colors.border.muted },
                    visibleLines.map((cL, cIdx) => (React.createElement(Text, { key: cIdx }, highlightCode(cL, ext)))),
                    isTruncated && (React.createElement(Text, { color: theme.colors.text.muted, italic: true },
                        "... [",
                        fileCodeLines.length - MAX_CODE_LINES,
                        " more lines collapsed]")))));
            idx++;
            continue;
        }
        // Code Block
        if (line.trim().startsWith('```')) {
            const lang = line.trim().replace(/^```/, '').toUpperCase() || 'CODE';
            const codeLines = [];
            idx++;
            while (idx < rawLines.length && !rawLines[idx].trim().startsWith('```')) {
                codeLines.push(rawLines[idx]);
                idx++;
            }
            idx++; // skip closing ```
            const MAX_CODE_LINES = 15;
            const isTruncated = codeLines.length > MAX_CODE_LINES;
            const visibleLines = isTruncated ? codeLines.slice(0, MAX_CODE_LINES) : codeLines;
            blocks.push(React.createElement(Box, { key: `code_${idx}`, flexDirection: "column", marginY: 1, width: "100%" },
                React.createElement(Box, { flexDirection: "row", justifyContent: "space-between", paddingX: 1, backgroundColor: theme.colors.bg.modal },
                    React.createElement(Text, { color: theme.colors.status.accent, bold: true },
                        "[",
                        lang,
                        "]"),
                    React.createElement(Text, { color: theme.colors.text.muted },
                        codeLines.length,
                        " ",
                        codeLines.length === 1 ? 'line' : 'lines',
                        isTruncated ? ` (showing 1-${MAX_CODE_LINES})` : '')),
                React.createElement(Box, { flexDirection: "column", paddingX: 1, paddingY: 0, borderStyle: "round", borderColor: theme.colors.border.muted },
                    visibleLines.map((cL, cIdx) => (React.createElement(Text, { key: cIdx }, highlightCode(cL, lang)))),
                    isTruncated && (React.createElement(Text, { color: theme.colors.text.muted, italic: true },
                        "... [",
                        codeLines.length - MAX_CODE_LINES,
                        " more lines collapsed]")))));
            continue;
        }
        // Markdown Table
        if (line.trim().startsWith('|') && idx + 1 < rawLines.length && rawLines[idx + 1].includes('---')) {
            const tableLines = [];
            while (idx < rawLines.length && rawLines[idx].trim().startsWith('|')) {
                tableLines.push(rawLines[idx]);
                idx++;
            }
            const table = parseTable(tableLines);
            if (table) {
                blocks.push(React.createElement(MarkdownTableRenderer, { key: `table_${idx}`, table: table }));
                continue;
            }
        }
        // H1 Header
        if (line.startsWith('# ')) {
            const title = line.slice(2).trim();
            blocks.push(React.createElement(Box, { key: `h1_${idx}`, flexDirection: "column", marginTop: 1, marginBottom: 1 },
                React.createElement(Text, { color: theme.colors.status.accent, bold: true }, title.toUpperCase()),
                React.createElement(Text, { color: theme.colors.border.muted }, '─'.repeat(Math.min(title.length + 8, 60)))));
            idx++;
            continue;
        }
        // H2 Header
        if (line.startsWith('## ')) {
            const title = line.slice(3).trim();
            blocks.push(React.createElement(Box, { key: `h2_${idx}`, flexDirection: "row", alignItems: "center", marginTop: 1, marginBottom: 0 },
                React.createElement(Text, { color: theme.colors.status.success, bold: true },
                    "\u25B8 ",
                    title)));
            idx++;
            continue;
        }
        // H3 Header
        if (line.startsWith('### ')) {
            const title = line.slice(4).trim();
            blocks.push(React.createElement(Box, { key: `h3_${idx}`, flexDirection: "row", alignItems: "center", marginTop: 1, marginBottom: 0 },
                React.createElement(Text, { color: theme.colors.text.bright, bold: true }, title)));
            idx++;
            continue;
        }
        // Bullet List
        if (/^\s*[-*+]\s+/.test(line)) {
            const itemText = line.replace(/^\s*[-*+]\s+/, '');
            blocks.push(React.createElement(Box, { key: `bullet_${idx}`, flexDirection: "row", paddingLeft: 1 },
                React.createElement(Text, { color: theme.colors.status.accent }, "\u25B8 "),
                React.createElement(FormattedInlineText, { text: itemText })));
            idx++;
            continue;
        }
        // Numbered List
        if (/^\s*\d+\.\s+/.test(line)) {
            const match = line.match(/^\s*(\d+\.)\s+(.*)/);
            const numStr = match ? match[1] : '1.';
            const itemText = match ? match[2] : line;
            blocks.push(React.createElement(Box, { key: `num_${idx}`, flexDirection: "row", paddingLeft: 1 },
                React.createElement(Text, { color: theme.colors.status.info, bold: true },
                    numStr,
                    ' '),
                React.createElement(FormattedInlineText, { text: itemText })));
            idx++;
            continue;
        }
        // Blank line
        if (!line.trim()) {
            blocks.push(React.createElement(Box, { key: `blank_${idx}`, height: 0 }));
            idx++;
            continue;
        }
        // Regular Text Paragraph
        blocks.push(React.createElement(Box, { key: `p_${idx}`, flexDirection: "row", paddingX: 0 },
            React.createElement(FormattedInlineText, { text: line })));
        idx++;
    }
    return (React.createElement(Box, { flexDirection: "column", width: "100%" }, blocks));
};
