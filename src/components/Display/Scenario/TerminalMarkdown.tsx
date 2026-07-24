import { Box, Text } from 'ink';
import React from 'react';
import { useTheme } from '../../../theme/ThemeContext';
import { highlightCode } from '../../../utils/syntaxHighlight';

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
  let match: RegExpExecArray | null;

  while ((match = regex.exec(text)) !== null) {
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
  }

  if (lastIdx < text.length) {
    tokens.push({ text: text.slice(lastIdx) });
  }

  return tokens;
}

const FormattedInlineText: React.FC<{ text: string }> = ({ text }) => {
  const { theme } = useTheme();
  const tokens = parseInlineTokens(text);

  return (
    <Text>
      {tokens.map((t, i) => {
        if (t.code) {
          return (
            <Text key={i} color={theme.colors.status.warning} backgroundColor={theme.colors.bg.card}>
              {` ${t.text} `}
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

const SyntaxHighlightedLine: React.FC<{ line: string }> = ({ line }) => {
  const { theme } = useTheme();

  if (line.trim().startsWith('#') || line.trim().startsWith('//')) {
    return <Text color={theme.colors.text.muted}>{line}</Text>;
  }

  const parts = line.split(/(\b(?:def|class|import|from|return|const|let|var|function|fn|pub|async|await|if|else|for|while|try|except|catch|raise|print|dict|str|int|bool|True|False|None|self)\b|".*?"|'.*?'|\b\d+\b)/g);

  const keywords = new Set([
    'def', 'class', 'import', 'from', 'return', 'const', 'let', 'var', 'function',
    'fn', 'pub', 'async', 'await', 'if', 'else', 'for', 'while', 'try', 'except',
    'catch', 'raise', 'print', 'dict', 'str', 'int', 'bool', 'True', 'False', 'None', 'self',
  ]);

  return (
    <Text>
      {parts.map((p, i) => {
        if (keywords.has(p)) {
          return (
            <Text key={i} color={theme.colors.status.info} bold>
              {p}
            </Text>
          );
        }
        if ((p.startsWith('"') && p.endsWith('"')) || (p.startsWith("'") && p.endsWith("'"))) {
          return (
            <Text key={i} color={theme.colors.status.success}>
              {p}
            </Text>
          );
        }
        if (/^\d+$/.test(p)) {
          return (
            <Text key={i} color={theme.colors.status.warning}>
              {p}
            </Text>
          );
        }
        return <Text key={i} color={theme.colors.text.ethereal}>{p}</Text>;
      })}
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

  const colWidths = table.headers.map((h, i) => {
    let max = h.length;
    table.rows.forEach((r) => {
      if (r[i] && r[i].length > max) {
        max = r[i].length;
      }
    });
    return Math.max(max, 6);
  });

  const makeRowStr = (cells: string[]) =>
    '│ ' + cells.map((cell, i) => (cell || '').padEnd(colWidths[i])).join(' │ ') + ' │';

  const topBorder = '┌─' + colWidths.map((w) => '─'.repeat(w)).join('─┬─') + '─┐';
  const headerSep = '├─' + colWidths.map((w) => '─'.repeat(w)).join('─┼─') + '─┤';
  const bottomBorder = '└─' + colWidths.map((w) => '─'.repeat(w)).join('─┴─') + '─┘';

  return (
    <Box flexDirection="column" marginY={1}>
      <Text color={theme.colors.border.muted}>{topBorder}</Text>
      <Box flexDirection="row">
        <Text color={theme.colors.text.bright} bold>
          {makeRowStr(table.headers)}
        </Text>
      </Box>
      <Text color={theme.colors.border.muted}>{headerSep}</Text>
      {table.rows.map((r, idx) => (
        <Box key={idx} flexDirection="row">
          <Text color={theme.colors.text.ethereal}>{makeRowStr(r)}</Text>
        </Box>
      ))}
      <Text color={theme.colors.border.muted}>{bottomBorder}</Text>
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

    // Code Block
    if (line.trim().startsWith('```')) {
      const lang = line.trim().replace(/^```/, '').toUpperCase() || 'CODE';
      const codeLines: string[] = [];
      idx++;
      while (idx < rawLines.length && !rawLines[idx].trim().startsWith('```')) {
        codeLines.push(rawLines[idx]);
        idx++;
      }
      idx++; // skip closing ```

      blocks.push(
        <Box key={`code_${idx}`} flexDirection="column" marginY={1} width="100%">
          <Box
            flexDirection="row"
            justifyContent="space-between"
            paddingX={1}
            backgroundColor={theme.colors.bg.card}
          >
            <Text color={theme.colors.status.accent} bold>
              [{lang}]
            </Text>
            <Text color={theme.colors.text.muted}>{codeLines.length} lines</Text>
          </Box>
          <Box
            flexDirection="column"
            paddingX={1}
            paddingY={0}
            borderStyle="single"
            borderColor={theme.colors.border.muted}
          >
            {codeLines.map((cL, cIdx) => (
              <Text key={cIdx}>{highlightCode(cL, lang)}</Text>
            ))}
          </Box>
        </Box>,
      );
      continue;
    }

    // Markdown Table
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

    // H1 Header
    if (line.startsWith('# ')) {
      const title = line.slice(2).trim();
      blocks.push(
        <Box key={`h1_${idx}`} flexDirection="column" marginTop={1} marginBottom={1}>
          <Text color={theme.colors.status.accent} bold>
            {title.toUpperCase()}
          </Text>
          <Text color={theme.colors.border.muted}>{'─'.repeat(Math.min(title.length + 8, 60))}</Text>
        </Box>,
      );
      idx++;
      continue;
    }

    // H2 Header
    if (line.startsWith('## ')) {
      const title = line.slice(3).trim();
      blocks.push(
        <Box key={`h2_${idx}`} flexDirection="row" alignItems="center" marginTop={1} marginBottom={0}>
          <Text color={theme.colors.status.success} bold>
            ▸ {title}
          </Text>
        </Box>,
      );
      idx++;
      continue;
    }

    // H3 Header
    if (line.startsWith('### ')) {
      const title = line.slice(4).trim();
      blocks.push(
        <Box key={`h3_${idx}`} flexDirection="row" alignItems="center" marginTop={1} marginBottom={0}>
          <Text color={theme.colors.text.bright} bold>
            {title}
          </Text>
        </Box>,
      );
      idx++;
      continue;
    }

    // Bullet List
    if (/^\s*[-*+]\s+/.test(line)) {
      const itemText = line.replace(/^\s*[-*+]\s+/, '');
      blocks.push(
        <Box key={`bullet_${idx}`} flexDirection="row" paddingLeft={1}>
          <Text color={theme.colors.status.accent}>▸ </Text>
          <FormattedInlineText text={itemText} />
        </Box>,
      );
      idx++;
      continue;
    }

    // Numbered List
    if (/^\s*\d+\.\s+/.test(line)) {
      const match = line.match(/^\s*(\d+\.)\s+(.*)/);
      const numStr = match ? match[1] : '1.';
      const itemText = match ? match[2] : line;
      blocks.push(
        <Box key={`num_${idx}`} flexDirection="row" paddingLeft={1}>
          <Text color={theme.colors.status.info} bold>
            {numStr}{' '}
          </Text>
          <FormattedInlineText text={itemText} />
        </Box>,
      );
      idx++;
      continue;
    }

    // Blank line
    if (!line.trim()) {
      blocks.push(<Box key={`blank_${idx}`} height={0} />);
      idx++;
      continue;
    }

    // Regular Text Paragraph
    blocks.push(
      <Box key={`p_${idx}`} flexDirection="row" paddingX={0}>
        <FormattedInlineText text={line} />
      </Box>,
    );
    idx++;
  }

  return <Box flexDirection="column" width="100%">{blocks}</Box>;
};
