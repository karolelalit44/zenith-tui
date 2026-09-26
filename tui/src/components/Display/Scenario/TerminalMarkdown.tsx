import { Box, Text } from 'ink';
import React from 'react';
import { TABLE_WIDTH_INSET } from '../../../constants/layout';
import { useTerminalDimensions } from '../../../hooks/useTerminalDimensions';
import { useTheme } from '../../../theme/ThemeContext';
import { highlightCode } from '../../../utils/syntaxHighlight';

interface TerminalMarkdownProps {
  content: string;
  isRunning?: boolean;
  maxLines?: number;
  scrollOffset?: number;
}

interface InlineToken {
  text: string;
  bold?: boolean;
  italic?: boolean;
  code?: boolean;
}

function parseInlineTokens(text: string): InlineToken[] {
  if (!text.includes('*') && !text.includes('`')) {
    return [{ text }];
  }
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

/** Remove markdown inline markers so table cells render as clean monospace text. */
function stripInlineMarkdown(text: string): string {
  return text
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/\*([^*]+)\*/g, '$1')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1');
}

function parseTable(lines: string[]): TableBlock | null {
  if (lines.length < 2) return null;
  const parseRow = (line: string) => {
    let clean = line.trim();
    if (clean.startsWith('|')) clean = clean.slice(1);
    if (clean.endsWith('|')) clean = clean.slice(0, -1);
    return clean.split('|').map((c) => c.trim());
  };

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

/**
 * Wraps cell text into lines that fit within the specified column width.
 * Splits on whitespace where possible; breaks long words that exceed width.
 */
function wrapCellText(text: string, width: number): string[] {
  if (width <= 0) return [''];
  if (!text) return [''];

  const normalized = text.trim();
  if (!normalized) return [''];

  const rawParagraphs = normalized.split('\n');
  const allLines: string[] = [];

  for (const para of rawParagraphs) {
    const trimmedPara = para.trim();
    if (!trimmedPara) {
      allLines.push('');
      continue;
    }

    const words = trimmedPara.split(/\s+/);
    let currentLine = '';

    for (const word of words) {
      if (!word) continue;

      // If word itself is longer than width, chunk it
      if (word.length > width) {
        if (currentLine) {
          allLines.push(currentLine);
          currentLine = '';
        }
        let remaining = word;
        while (remaining.length > width) {
          allLines.push(remaining.slice(0, width));
          remaining = remaining.slice(width);
        }
        currentLine = remaining;
        continue;
      }

      if (!currentLine) {
        currentLine = word;
      } else if (currentLine.length + 1 + word.length <= width) {
        currentLine += ` ${word}`;
      } else {
        allLines.push(currentLine);
        currentLine = word;
      }
    }

    if (currentLine) {
      allLines.push(currentLine);
    }
  }

  return allLines.length > 0 ? allLines : [''];
}

/**
 * Computes optimal column widths given terminal constraints.
 * Ensures columns that fit within their fair share only consume what they need,
 * allowing wider columns to utilize the remaining available width.
 */
function computeColWidths(headers: string[], rows: string[][], availCellWidth: number): number[] {
  const numCols = headers.length || 1;
  const MIN_COL_WIDTH = 3;

  const desiredWidths = headers.map((h, i) => {
    let max = Math.max(h.length, MIN_COL_WIDTH);
    for (const r of rows) {
      const cell = r[i] || '';
      const lines = cell.includes('\n') ? cell.split('\n') : [cell];
      for (const line of lines) {
        if (line.length > max) {
          max = line.length;
        }
      }
    }
    return max;
  });

  const totalDesired = desiredWidths.reduce((sum, w) => sum + w, 0);
  if (totalDesired <= availCellWidth) {
    return desiredWidths;
  }

  const colWidths = new Array(numCols).fill(0);
  let remainingWidth = availCellWidth;
  let remainingCols = numCols;
  const finalized = new Array(numCols).fill(false);

  let changed = true;
  while (changed && remainingCols > 0) {
    changed = false;
    const fairShare = Math.floor(remainingWidth / remainingCols);

    for (let i = 0; i < numCols; i++) {
      if (!finalized[i] && desiredWidths[i] <= fairShare) {
        const allocated = Math.max(MIN_COL_WIDTH, desiredWidths[i]);
        colWidths[i] = allocated;
        remainingWidth -= allocated;
        remainingCols--;
        finalized[i] = true;
        changed = true;
      }
    }
  }

  if (remainingCols > 0) {
    const baseShare = Math.max(MIN_COL_WIDTH, Math.floor(remainingWidth / remainingCols));
    let remainder = Math.max(0, remainingWidth - baseShare * remainingCols);

    for (let i = 0; i < numCols; i++) {
      if (!finalized[i]) {
        const extra = remainder > 0 ? 1 : 0;
        remainder = Math.max(0, remainder - 1);
        colWidths[i] = Math.min(desiredWidths[i], baseShare + extra);
        colWidths[i] = Math.max(MIN_COL_WIDTH, colWidths[i]);
      }
    }
  }

  return colWidths;
}

function formatRowLines(cells: string[], colWidths: number[]): string[] {
  const wrappedCols = colWidths.map((width, i) => wrapCellText(cells[i] || '', width));
  const maxLines = Math.max(1, ...wrappedCols.map((col) => col.length));

  const result: string[] = [];
  for (let lineIdx = 0; lineIdx < maxLines; lineIdx++) {
    const lineCells = colWidths.map((width, i) => {
      const text = wrappedCols[i][lineIdx] || '';
      return text.padEnd(width, ' ');
    });
    result.push(`│ ${lineCells.join(' │ ')} │`);
  }
  return result;
}

const MarkdownTableRenderer: React.FC<{ table: TableBlock }> = ({ table }) => {
  const { theme } = useTheme();
  const { columns } = useTerminalDimensions();

  const headers = table.headers.map(stripInlineMarkdown);
  const rows = table.rows.map((r) => r.map(stripInlineMarkdown));

  const numCols = Math.max(headers.length, ...rows.map((r) => r.length), 1);
  while (headers.length < numCols) headers.push('');

  const maxTableWidth = Math.max(24, columns - TABLE_WIDTH_INSET);
  // Account for table borders: "│ " (2) + " │ " (3 * (numCols - 1)) + " │" (2) = 4 + 3*(numCols - 1)
  const overhead = 4 + 3 * (numCols - 1);
  const availCellWidth = Math.max(numCols * 3, maxTableWidth - overhead);

  const colWidths = computeColWidths(headers, rows, availCellWidth);

  const topBorder = `┌─${colWidths.map((w) => '─'.repeat(w)).join('─┬─')}─┐`;
  const headerSep = `├─${colWidths.map((w) => '─'.repeat(w)).join('─┼─')}─┤`;
  const bottomBorder = `└─${colWidths.map((w) => '─'.repeat(w)).join('─┴─')}─┘`;

  const headerLines = formatRowLines(headers, colWidths);

  return (
    <Box flexDirection="column" marginTop={1} width="100%">
      <Text color={theme.colors.border.muted} wrap="truncate-end">
        {topBorder}
      </Text>
      <Box flexDirection="column" width="100%">
        {headerLines.map((lineStr, lineIdx) => (
          <Text key={lineIdx} color={theme.colors.text.bright} bold wrap="truncate-end">
            {lineStr}
          </Text>
        ))}
      </Box>
      <Text color={theme.colors.border.muted} wrap="truncate-end">
        {headerSep}
      </Text>
      {rows.map((r, idx) => {
        const rowLines = formatRowLines(r, colWidths);
        return (
          <Box key={idx} flexDirection="column" width="100%">
            {rowLines.map((lineStr, lineIdx) => (
              <Text key={lineIdx} color={theme.colors.text.ethereal} wrap="truncate-end">
                {lineStr}
              </Text>
            ))}
          </Box>
        );
      })}
      <Text color={theme.colors.border.muted} wrap="truncate-end">
        {bottomBorder}
      </Text>
    </Box>
  );
};

export const TerminalMarkdown: React.FC<TerminalMarkdownProps> = ({
  content,
  isRunning = false,
  maxLines,
  scrollOffset,
}) => {
  const { theme } = useTheme();
  const { columns } = useTerminalDimensions();
  const termCols = columns || process.stdout.columns || 80;
  // Horizontal rules span the content column (App paddingX + widget inset).
  const hrWidth = Math.max(20, termCols - TABLE_WIDTH_INSET);

  if (!content) return null;

  const allRawLines = content.split('\n');
  const shouldWindow = isRunning && Boolean(maxLines && maxLines > 0 && allRawLines.length > maxLines);

  let rawLines = allRawLines;
  let hiddenAbove = 0;
  let hiddenBelow = 0;

  if (shouldWindow && maxLines) {
    const total = allRawLines.length;
    const maxOffset = Math.max(0, total - maxLines);
    const start = scrollOffset !== undefined ? Math.max(0, Math.min(maxOffset, scrollOffset)) : maxOffset;
    const end = Math.min(total, start + maxLines);

    hiddenAbove = start;
    hiddenBelow = total - end;

    let inCode = false;
    let codeLang = '';
    for (let i = 0; i < start; i++) {
      const trimmed = allRawLines[i].trim();
      if (trimmed.startsWith('```')) {
        if (inCode) {
          inCode = false;
          codeLang = '';
        } else {
          inCode = true;
          codeLang = trimmed.replace(/^```/, '');
        }
      }
    }

    const sliced = allRawLines.slice(start, end);
    if (inCode) {
      sliced.unshift(`\`\`\`${codeLang}`);
    }
    let sliceInCode = inCode;
    for (const l of sliced) {
      if (l.trim().startsWith('```')) {
        sliceInCode = !sliceInCode;
      }
    }
    if (sliceInCode) {
      sliced.push(`${'`'.repeat(3)} ⋯ (continued below)`);
    }
    rawLines = sliced;
  }

  const blocks: React.ReactNode[] = [];
  let idx = 0;

  while (idx < rawLines.length) {
    const line = rawLines[idx];

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
        diffStatsStr = parts.length > 0 ? `${parts.join(' ')} lines` : `${codeLines.length} lines`;
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
                <Text color={theme.colors.status.info} bold>
                  ▸ {lang === 'DIFF' ? 'diff' : lang.toLowerCase()}
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
                        <Text color={theme.colors.text.dim}>{' '.repeat(gutterWidth)} │ </Text>
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

    if (/^\s*(?:---+|\*{3,}|_{3,}|—{2,}|─{2,})\s*$/.test(line)) {
      blocks.push(
        <Box key={`hr_${idx}`} width="100%">
          <Text color={theme.colors.border.muted} dimColor wrap="truncate-end">
            {'─'.repeat(hrWidth)}
          </Text>
        </Box>,
      );
      idx++;
      continue;
    }

    if (!line.trim()) {
      // Collapse consecutive blank lines into a single spacer and drop
      // trailing blanks so the response body never shows double-height gaps.
      let run = 0;
      while (idx + run < rawLines.length && !rawLines[idx + run].trim()) {
        run += 1;
      }
      if (idx + run < rawLines.length) {
        blocks.push(<Box key={`blank_${idx}`} height={1} />);
      }
      idx += run;
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
      {hiddenAbove > 0 && (
        <Box paddingLeft={1} marginBottom={0}>
          <Text color={theme.colors.text.dim} dimColor italic>
            ▲ {hiddenAbove} earlier lines (PgUp to view)
          </Text>
        </Box>
      )}
      {blocks}
      {hiddenBelow > 0 && (
        <Box paddingLeft={1} marginTop={0}>
          <Text color={theme.colors.text.dim} dimColor italic>
            ▼ {hiddenBelow} lines below (PgDn to follow)
          </Text>
        </Box>
      )}
    </Box>
  );
};
