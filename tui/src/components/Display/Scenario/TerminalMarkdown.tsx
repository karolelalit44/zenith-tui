import { Box, Text } from 'ink';
import React from 'react';
import { useTerminalDimensions } from '../../../hooks/useTerminalDimensions';
import { useTheme } from '../../../theme/ThemeContext';
import { highlightCode } from '../../../utils/syntaxHighlight';
import { truncateEnd } from '../../../utils/text';

interface TerminalMarkdownProps {
  content: string;
}

interface InlineToken {
  text: string;
  bold?: boolean;
  italic?: boolean;
  code?: boolean;
}

function parseInlineTokens(text: string): InlineToken[] {
  const tokens: InlineToken[] = [];
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
    } else if (matched.startsWith('*') && matched.endsWith('*')) {
      tokens.push({ text: matched.slice(1, -1), italic: true });
    } else if (matched.startsWith('`') && matched.endsWith('`')) {
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

const FormattedInlineText: React.FC<{ text: string }> = ({ text }) => {
  const { theme } = useTheme();
  const tokens = parseInlineTokens(text);

  // Render inline tokens as a single flat <Text wrap="wrap"> node.
  // All children must be plain <Text> siblings — no nesting — so Ink can
  // compute a single contiguous ANSI string and wrap it cleanly without
  // emitting partial escape sequences at line boundaries.
  return (
    <Text wrap="wrap">
      {tokens.map((t, i) => {
        if (t.code) {
          return (
            <Text key={i} color={theme.colors.status.warning} bold>
              {t.text}
            </Text>
          );
        }
        if (t.bold) {
          return (
            <Text key={i} color={theme.colors.text.bright} bold>
              {t.text}
            </Text>
          );
        }
        if (t.italic) {
          return (
            <Text key={i} color={theme.colors.text.ethereal} italic>
              {t.text}
            </Text>
          );
        }
        return (
          <Text key={i} color={theme.colors.text.ethereal}>
            {t.text}
          </Text>
        );
      })}
    </Text>
  );
};

/** Renders a highlighted code line using the theme-driven segment API. */
const CodeText: React.FC<{ text: string; lang?: string }> = ({ text, lang }) => {
  const { theme } = useTheme();
  const segments = highlightCode(text, theme, lang?.trim() ? lang.toLowerCase() : undefined);
  return (
    <Text wrap="wrap">
      {segments.map((seg, i) => (
        <Text key={i} color={seg.color}>
          {seg.text}
        </Text>
      ))}
    </Text>
  );
};

interface TableBlock {
  headers: string[];
  rows: string[][];
}

function parseTable(lines: string[]): TableBlock | null {
  if (lines.length < 2) return null;
  const parseRow = (line: string) =>
    line
      .trim()
      .slice(1, -1)
      .split('|')
      .map((c) => c.trim());

  const headers = parseRow(lines[0]);
  if (!lines[1].includes('---')) return null;

  const rows: string[][] = [];
  for (let i = 2; i < lines.length; i++) {
    if (lines[i].includes('|')) {
      rows.push(parseRow(lines[i]));
    }
  }

  return { headers, rows };
}

const MarkdownTableRenderer: React.FC<{ table: TableBlock }> = ({ table }) => {
  const { theme } = useTheme();
  const { columns } = useTerminalDimensions();

  const numCols = table.headers.length || 1;
  const maxTableWidth = Math.max(24, columns - 6);
  // Account for table borders: "│ " (2) + " │ " (3 * (numCols - 1)) + " │" (2) = 4 + 3*(numCols - 1)
  const overhead = 4 + 3 * (numCols - 1);
  const availCellWidth = Math.max(numCols * 4, maxTableWidth - overhead);
  const colBudget = Math.max(4, Math.floor(availCellWidth / numCols));

  const colWidths = table.headers.map((h, i) => {
    let max = h.length;
    table.rows.forEach((r) => {
      if (r[i] && r[i].length > max) {
        max = r[i].length;
      }
    });
    return Math.max(4, Math.min(max, colBudget));
  });

  const makeRowStr = (cells: string[]) =>
    `│ ${cells.map((cell, i) => (truncateEnd(cell || '', colWidths[i]) || '').padEnd(colWidths[i])).join(' │ ')} │`;

  const topBorder = `┌─${colWidths.map((w) => '─'.repeat(w)).join('─┬─')}─┐`;
  const headerSep = `├─${colWidths.map((w) => '─'.repeat(w)).join('─┼─')}─┤`;
  const bottomBorder = `└─${colWidths.map((w) => '─'.repeat(w)).join('─┴─')}─┘`;

  return (
    <Box flexDirection="column" marginTop={1} width="100%">
      <Text color={theme.colors.border.muted} wrap="truncate-end">
        {topBorder}
      </Text>
      <Box flexDirection="row" width="100%">
        <Text color={theme.colors.text.bright} bold wrap="truncate-end">
          {makeRowStr(table.headers)}
        </Text>
      </Box>
      <Text color={theme.colors.border.muted} wrap="truncate-end">
        {headerSep}
      </Text>
      {table.rows.map((r, idx) => (
        <Box key={idx} flexDirection="row" width="100%">
          <Text color={theme.colors.text.ethereal} wrap="truncate-end">
            {makeRowStr(r)}
          </Text>
        </Box>
      ))}
      <Text color={theme.colors.border.muted} wrap="truncate-end">
        {bottomBorder}
      </Text>
    </Box>
  );
};

export const TerminalMarkdown: React.FC<TerminalMarkdownProps> = ({ content }) => {
  const { theme } = useTheme();

  if (!content) return null;

  const rawLines = content.split('\n');
  const blocks: React.ReactNode[] = [];
  let idx = 0;

  while (idx < rawLines.length) {
    const line = rawLines[idx];

    const fileWriteMatch = line.trim().match(/^\[file_write\s+path=["']([^"']+)["']\s+content=["']([\s\S]*)["']\]?$/);
    if (fileWriteMatch) {
      const rawPath = fileWriteMatch[1];
      const winPath = rawPath.replace(/\//g, '\\');
      const rawContent = fileWriteMatch[2].replace(/\\n/g, '\n').replace(/\\"/g, '"');
      const ext = rawPath.split('.').pop() || 'text';
      const fileCodeLines = rawContent.split('\n');
      const MAX_CODE_LINES = 15;
      const isTruncated = fileCodeLines.length > MAX_CODE_LINES;
      const visibleLines = isTruncated ? fileCodeLines.slice(0, MAX_CODE_LINES) : fileCodeLines;
      const gutterWidth = Math.max(2, String(fileCodeLines.length).length);

      blocks.push(
        <Box key={`filewrite_${idx}`} flexDirection="column" marginTop={1} width="100%">
          {}
          <Box flexDirection="row" alignItems="center" marginBottom={0}>
            <Text color={theme.colors.status.success} bold>
              ●{' '}
            </Text>
            <Text color={theme.colors.status.success} bold>
              Update({winPath})
            </Text>
          </Box>
          {}
          <Box flexDirection="row" alignItems="center" paddingLeft={1} marginBottom={0}>
            <Text color={theme.colors.text.dim}>└ </Text>
            <Text color={theme.colors.text.dim}>
              {fileCodeLines.length} {fileCodeLines.length === 1 ? 'line' : 'lines'}
            </Text>
          </Box>
          {}
          <Box flexDirection="column" paddingLeft={3} marginTop={0}>
            {visibleLines.map((cL, cIdx) => {
              const numStr = String(cIdx + 1).padStart(gutterWidth, ' ');
              return (
                <Box key={cIdx} width="100%">
                  <Text color={theme.colors.text.dim}>{numStr} </Text>
                  <CodeText text={cL} lang={ext} />
                </Box>
              );
            })}
            {isTruncated && (
              <Text color={theme.colors.text.dim} italic>
                ... [{fileCodeLines.length - MAX_CODE_LINES} more lines]
              </Text>
            )}
          </Box>
        </Box>,
      );
      idx++;
      continue;
    }

    if (line.trim().startsWith('```')) {
      const lang = line.trim().replace(/^```/, '').toUpperCase() || 'CODE';
      const codeLines: string[] = [];
      idx++;
      while (idx < rawLines.length && !rawLines[idx].trim().startsWith('```')) {
        codeLines.push(rawLines[idx]);
        idx++;
      }
      idx++;

      const MAX_CODE_LINES = 25;
      const isTruncated = codeLines.length > MAX_CODE_LINES;
      const visibleLines = isTruncated ? codeLines.slice(0, MAX_CODE_LINES) : codeLines;

      let removedCount = 0;
      let addedCount = 0;
      if (lang === 'DIFF') {
        for (const cL of codeLines) {
          if (cL.startsWith('-') && !cL.startsWith('---')) removedCount++;
          if (cL.startsWith('+') && !cL.startsWith('+++')) addedCount++;
        }
      }

      let diffStatsStr = '';
      if (lang === 'DIFF') {
        const parts: string[] = [];
        if (addedCount) parts.push(`+${addedCount}`);
        if (removedCount) parts.push(`-${removedCount}`);
        diffStatsStr = parts.length > 0 ? `L ${parts.join(' ')} lines` : `L ${codeLines.length} lines`;
      }

      const gutterWidth = Math.max(2, String(codeLines.length).length);
      let lineCounter = 1;

      blocks.push(
        <Box key={`code_${idx}`} flexDirection="column" marginTop={1} marginBottom={1} width="100%" paddingX={1}>
          <Box
            flexDirection="column"
            backgroundColor={theme.colors.code.background}
            borderStyle="round"
            borderColor={theme.colors.border.muted}
            paddingX={1}
            paddingY={0}
          >
            {/* Designer Terminal Window Header Bar */}
            <Box flexDirection="row" alignItems="center" width="100%" flexWrap="nowrap">
              <Box flexDirection="row" alignItems="center" flexGrow={1} flexShrink={1} overflow="hidden">
                <Text color={theme.colors.decorative.trafficLight.red}>● </Text>
                <Text color={theme.colors.decorative.trafficLight.yellow}>● </Text>
                <Text color={theme.colors.decorative.trafficLight.green}>● </Text>
                <Text color={theme.colors.status.info} bold wrap="truncate-end">
                  {lang === 'DIFF' ? 'diff' : lang.toLowerCase()}
                </Text>
                {lang === 'DIFF' && diffStatsStr ? (
                  <>
                    <Text color={theme.colors.text.dim}> · </Text>
                    <Text color={theme.colors.text.muted} wrap="truncate-end">
                      {diffStatsStr}
                    </Text>
                  </>
                ) : null}
              </Box>
            </Box>

            {/* Code Body with Line Numbers & Syntax Highlighting */}
            <Box flexDirection="column" marginTop={0}>
              {visibleLines.map((cL, cIdx) => {
                if (lang === 'DIFF') {
                  const hunkMatch = cL.match(/^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@/);
                  if (hunkMatch) {
                    lineCounter = parseInt(hunkMatch[1], 10);
                    return (
                      <Box key={cIdx} width="100%">
                        <Text color={theme.colors.text.dim}>{cL}</Text>
                      </Box>
                    );
                  }

                  if (cL.startsWith('-') && !cL.startsWith('---')) {
                    const numStr = String(lineCounter).padStart(gutterWidth, ' ');
                    const cleanContent = cL.startsWith('- ') ? cL.slice(2) : cL.slice(1);
                    return (
                      <Box key={cIdx} backgroundColor={theme.colors.diff.removeBg} width="100%">
                        <Text color={theme.colors.diff.removeFg}>{numStr} - </Text>
                        <Text color={theme.colors.diff.removeFg}>{cleanContent}</Text>
                      </Box>
                    );
                  }

                  if (cL.startsWith('+') && !cL.startsWith('+++')) {
                    const numStr = String(lineCounter).padStart(gutterWidth, ' ');
                    const cleanContent = cL.startsWith('+ ') ? cL.slice(2) : cL.slice(1);
                    lineCounter++;
                    return (
                      <Box key={cIdx} backgroundColor={theme.colors.diff.addBg} width="100%">
                        <Text color={theme.colors.diff.addFg}>{numStr} + </Text>
                        <Text color={theme.colors.diff.addFg}>{cleanContent}</Text>
                      </Box>
                    );
                  }

                  const numStr = String(lineCounter).padStart(gutterWidth, ' ');
                  const cleanContent = cL.startsWith(' ') ? cL.slice(1) : cL;
                  lineCounter++;
                  return (
                    <Box key={cIdx} width="100%">
                      <Text color={theme.colors.text.dim}>{numStr} │ </Text>
                      <Text color={theme.colors.text.bright}>{cleanContent}</Text>
                    </Box>
                  );
                }

                const numStr = String(cIdx + 1).padStart(gutterWidth, ' ');
                return (
                  <Box key={cIdx} width="100%">
                    <Text color={theme.colors.text.dim}>{numStr} │ </Text>
                    <CodeText text={cL} lang={lang.toLowerCase()} />
                  </Box>
                );
              })}
              {isTruncated && (
                <Box width="100%" marginTop={0}>
                  <Text color={theme.colors.text.dim} italic>
                    … [{codeLines.length - MAX_CODE_LINES} more lines]
                  </Text>
                </Box>
              )}
            </Box>
          </Box>
        </Box>,
      );
      continue;
    }

    if (line.trim().startsWith('|') && idx + 1 < rawLines.length && rawLines[idx + 1].includes('---')) {
      const tableLines: string[] = [];
      while (idx < rawLines.length && rawLines[idx].trim().startsWith('|')) {
        tableLines.push(rawLines[idx]);
        idx++;
      }
      const table = parseTable(tableLines);
      if (table) {
        blocks.push(<MarkdownTableRenderer key={`table_${idx}`} table={table} />);
        continue;
      }
    }

    if (line.startsWith('# ')) {
      const title = line.slice(2).trim();
      blocks.push(
        <Box key={`h1_${idx}`} flexDirection="column" marginBottom={1}>
          <Text color={theme.colors.text.heading} bold>
            {title}
          </Text>
        </Box>,
      );
      idx++;
      continue;
    }

    if (line.startsWith('## ')) {
      const title = line.slice(3).trim();
      blocks.push(
        <Box key={`h2_${idx}`} flexDirection="row" alignItems="center" marginBottom={1}>
          <Text color={theme.colors.text.heading} bold>
            {title}
          </Text>
        </Box>,
      );
      idx++;
      continue;
    }

    if (line.startsWith('### ')) {
      const title = line.slice(4).trim();
      blocks.push(
        <Box key={`h3_${idx}`} flexDirection="row" alignItems="center" marginBottom={1}>
          <Text color={theme.colors.text.bright} bold>
            {title}
          </Text>
        </Box>,
      );
      idx++;
      continue;
    }

    if (/^\s*[-*+]\s+\[([ xX/~])\]\s+/.test(line)) {
      const match = line.match(/^\s*[-*+]\s+\[([ xX/~])\]\s+(.*)/);
      if (match) {
        const mark = match[1].toLowerCase();
        const itemText = match[2];
        let symbol = '□';
        let symbolColor = theme.colors.text.dim;
        let isDone = false;
        let isActive = false;

        if (mark === 'x') {
          symbol = '■';
          symbolColor = theme.colors.status.warning;
          isDone = true;
        } else if (mark === '/' || mark === '~') {
          symbol = '▶';
          symbolColor = theme.colors.status.info;
          isActive = true;
        }

        blocks.push(
          <Box key={`task_${idx}`} flexDirection="row" paddingLeft={1} width="100%">
            <Box width={2}>
              <Text color={symbolColor}>{symbol}</Text>
            </Box>
            <Box flexShrink={1}>
              <Text
                wrap="wrap"
                color={
                  isDone ? theme.colors.text.bright : isActive ? theme.colors.text.bright : theme.colors.text.muted
                }
              >
                {itemText}
              </Text>
            </Box>
          </Box>,
        );
        idx++;
        continue;
      }
    }

    if (/^\s*[└├│]/.test(line)) {
      blocks.push(
        <Box key={`tree_${idx}`} flexDirection="row" paddingLeft={1} width="100%">
          <Text color={theme.colors.text.dim} wrap="wrap">
            {line}
          </Text>
        </Box>,
      );
      idx++;
      continue;
    }

    if (/^\s*[-*+]\s+/.test(line)) {
      const itemText = line.replace(/^\s*[-*+]\s+/, '');
      blocks.push(
        <Box key={`bullet_${idx}`} flexDirection="row" paddingLeft={1} width="100%">
          <Text color={theme.colors.status.accent}>▸ </Text>
          <Box flexShrink={1} flexGrow={1}>
            <FormattedInlineText text={itemText} />
          </Box>
        </Box>,
      );
      idx++;
      continue;
    }

    if (/^\s*\d+\.\s+/.test(line)) {
      const match = line.match(/^\s*(\d+\.)\s+(.*)/);
      const numStr = match ? match[1] : '1.';
      const itemText = match ? match[2] : line;
      blocks.push(
        <Box key={`num_${idx}`} flexDirection="row" paddingLeft={1} width="100%">
          <Text color={theme.colors.status.info} bold>
            {numStr}{' '}
          </Text>
          <Box flexShrink={1} flexGrow={1}>
            <FormattedInlineText text={itemText} />
          </Box>
        </Box>,
      );
      idx++;
      continue;
    }

    if (!line.trim()) {
      blocks.push(<Box key={`blank_${idx}`} height={1} />);
      idx++;
      continue;
    }

    // Plain paragraph — render with a constrained Box so Ink's yoga layout
    // correctly accounts for the available width before wrapping the text.
    // This prevents the ANSI reset + continuation sequence from appearing as
    // a stray character (e.g. `'` or backtick) at column 0 on the next line.
    blocks.push(
      <Box key={`p_${idx}`} flexDirection="row" width="100%">
        <Box flexShrink={1} flexGrow={1} overflow="hidden">
          <FormattedInlineText text={line} />
        </Box>
      </Box>,
    );
    idx++;
  }

  return (
    <Box flexDirection="column" width="100%">
      {blocks}
    </Box>
  );
};
