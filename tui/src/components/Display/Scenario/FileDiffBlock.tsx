import { Box, Text } from 'ink';
import React from 'react';
import { useTheme } from '../../../theme/ThemeContext';
import type { Theme } from '../../../theme/theme';
import { highlightCode } from '../../../utils/syntaxHighlight';

const GUTTER_NUM_WIDTH = 4;

export interface DiffLine {
  type: 'add' | 'delete' | 'hunk' | 'normal';
  oldLineNumber?: number;
  newLineNumber?: number;
  content: string;
}

/** Split code into whitespace-delimited tokens (whitespace preserved). */
function tokenize(line: string): string[] {
  return line.match(/\S+|\s+/g) ?? [];
}

function diffMasks(removed: string[], added: string[]): { removedFlags: boolean[]; addedFlags: boolean[] } {
  const n = removed.length;
  const m = added.length;
  const dp: number[][] = Array.from({ length: n + 1 }, () => new Array<number>(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      dp[i][j] = removed[i] === added[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }
  const removedFlags = new Array<boolean>(n).fill(true);
  const addedFlags = new Array<boolean>(m).fill(true);
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (removed[i] === added[j]) {
      removedFlags[i] = false;
      addedFlags[j] = false;
      i++;
      j++;
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      i++;
    } else {
      j++;
    }
  }
  return { removedFlags, addedFlags };
}

function tokenFlagsToCharMask(content: string, tokenFlags?: boolean[]): boolean[] {
  const tokens = tokenize(content);
  const mask = new Array<boolean>(content.length).fill(false);
  if (!tokenFlags) return mask;
  let pos = 0;
  for (let t = 0; t < tokens.length && pos < content.length; t++) {
    const flag = tokenFlags[t] ?? false;
    for (let c = pos; c < pos + tokens[t].length; c++) mask[c] = flag;
    pos += tokens[t].length;
  }
  return mask;
}

function charColors(content: string, theme: Theme, language?: string): string[] {
  const colors = new Array<string>(content.length).fill(theme.colors.text.ethereal);
  let pos = 0;
  for (const seg of highlightCode(content, theme, language)) {
    for (let c = pos; c < pos + seg.text.length && c < content.length; c++) colors[c] = seg.color;
    pos += seg.text.length;
  }
  return colors;
}

function contentNodes(
  content: string,
  colors: string[],
  mask: boolean[] | undefined,
  changedFg?: string,
  changedBg?: string,
): React.ReactNode[] {
  const length = Math.min(content.length, colors.length);
  const changedMask = mask ?? new Array<boolean>(length).fill(false);
  const nodes: React.ReactNode[] = [];
  let index = 0;
  while (index < length) {
    const changed = changedMask[index];
    const color = changed && changedFg ? changedFg : colors[index];
    let runEnd = index + 1;
    while (runEnd < length && changedMask[runEnd] === changed && (changed || colors[runEnd] === color)) {
      runEnd++;
    }
    nodes.push(
      <Text key={index} color={color} backgroundColor={changed ? changedBg : undefined}>
        {content.slice(index, runEnd)}
      </Text>,
    );
    index = runEnd;
  }
  return nodes;
}

/** Render line gutter matching Claude Code / Gemini CLI standards. */
function renderGutter(
  line: DiffLine,
  theme: Theme,
  isAdd: boolean,
  isDelete: boolean,
  hasBoth: boolean,
  isUnifiedDiff: boolean,
) {
  const width = GUTTER_NUM_WIDTH;

  if (!isUnifiedDiff) {
    // Plain code format for untracked / newly written files
    const numStr = (line.newLineNumber !== undefined ? String(line.newLineNumber) : '').padStart(width);
    return (
      <Box flexDirection="row" marginRight={1} flexShrink={0}>
        <Text color={theme.colors.code.lineNum}>{numStr}</Text>
        <Text color={theme.colors.text.dim}> | </Text>
      </Box>
    );
  }

  // Native Git Diff format for tracked file patches
  const numColor = isAdd
    ? theme.colors.status.success
    : isDelete
      ? theme.colors.status.error
      : theme.colors.code.lineNum;

  if (hasBoth) {
    const oldStr = (line.oldLineNumber !== undefined ? String(line.oldLineNumber) : '').padStart(width);
    const newStr = (line.newLineNumber !== undefined ? String(line.newLineNumber) : '').padStart(width);
    return (
      <Box flexDirection="row" marginRight={1} flexShrink={0}>
        <Text color={numColor}>{oldStr}</Text>
        <Text color={theme.colors.text.dim}> | </Text>
        <Text color={numColor}>{newStr}</Text>
        <Text color={theme.colors.text.dim}> | </Text>
      </Box>
    );
  }

  const num = line.newLineNumber ?? line.oldLineNumber;
  const numStr = (num !== undefined ? String(num) : '').padStart(width);

  return (
    <Box flexDirection="row" marginRight={1} flexShrink={0}>
      <Text color={numColor}>{numStr}</Text>
      <Text color={theme.colors.text.dim}> | </Text>
    </Box>
  );
}

/** Build a compact hunk-only unified diff string from before/after content.
 *
 * Used as a frontend fallback when a file_edit event carries no server-recorded
 * diff (e.g. legacy replay). Line numbers are hunk-local since the full file is
 * unavailable at render time.
 */
export function buildUnifiedDiff(oldContent: string, newContent: string): string {
  const split = (text: string) => {
    const lines = text.replace(/\r\n/g, '\n').split('\n');
    if (lines.length > 0 && lines[lines.length - 1] === '') lines.pop();
    return lines;
  };
  const a = split(oldContent);
  const b = split(newContent);
  if (a.length === 0 && b.length === 0) return '';

  const n = a.length;
  const m = b.length;
  const dp: number[][] = Array.from({ length: n + 1 }, () => new Array<number>(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }
  const ops: { kind: 'del' | 'add'; text: string }[] = [];
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (a[i] === b[j]) {
      i++;
      j++;
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      ops.push({ kind: 'del', text: a[i++] });
    } else {
      ops.push({ kind: 'add', text: b[j++] });
    }
  }
  while (i < n) ops.push({ kind: 'del', text: a[i++] });
  while (j < m) ops.push({ kind: 'add', text: b[j++] });

  let delCount = 0;
  let addCount = 0;
  for (const op of ops) {
    if (op.kind === 'del') delCount++;
    else addCount++;
  }
  const header = `@@ -1${delCount > 1 ? `,${delCount}` : ''} +1${addCount > 1 ? `,${addCount}` : ''} @@`;
  const body = ops.map((op) => (op.kind === 'del' ? `-${op.text}` : `+${op.text}`));
  return [header, ...body, ''].join('\n');
}

export function parseDiffOrContent(text: string, maxLines = 30): { lines: DiffLine[]; isUnifiedDiff: boolean } {
  if (!text?.trim()) return { lines: [], isUnifiedDiff: false };

  const lines = text.split('\n');
  while (lines.length > 0 && lines[lines.length - 1].trim() === '') {
    lines.pop();
  }
  const isUnifiedDiff = lines.some((l) => l.startsWith('@@') || l.startsWith('diff --git'));

  const result: DiffLine[] = [];

  let curOld = 1;
  let curNew = 1;

  for (let i = 0; i < lines.length && result.length < maxLines; i++) {
    const line = lines[i];

    if (isUnifiedDiff) {
      if (line.startsWith('+++') || line.startsWith('---') || line.startsWith('diff --git')) {
        continue;
      }
      if (line.startsWith('@@')) {
        const match = line.match(/@@\s+-(\d+)(?:,\d+)?\s+\+(\d+)(?:,\d+)?\s+@@/);
        if (match) {
          curOld = parseInt(match[1], 10);
          curNew = parseInt(match[2], 10);
        }
        result.push({ type: 'hunk', content: line });
      } else if (line.startsWith('+')) {
        result.push({
          type: 'add',
          newLineNumber: curNew++,
          content: line.slice(1),
        });
      } else if (line.startsWith('-')) {
        result.push({
          type: 'delete',
          oldLineNumber: curOld++,
          content: line.slice(1),
        });
      } else {
        const content = line.startsWith(' ') ? line.slice(1) : line;
        result.push({
          type: 'normal',
          oldLineNumber: curOld++,
          newLineNumber: curNew++,
          content,
        });
      }
    } else {
      // Raw content for newly written files (Git Diff Addition View)
      result.push({
        type: 'add',
        newLineNumber: curNew++,
        content: line,
      });
    }
  }

  return { lines: result, isUnifiedDiff };
}

export function detectLanguageFromFilename(filename?: string): string | undefined {
  if (!filename) return undefined;
  const base = filename.replace(/\\/g, '/').split('/').pop() || '';
  if (base === 'Dockerfile' || base.startsWith('Dockerfile.')) return 'dockerfile';
  if (base === 'Makefile') return 'makefile';
  const ext = base.split('.').pop()?.toLowerCase();
  switch (ext) {
    case 'py':
      return 'python';
    case 'ts':
    case 'tsx':
      return 'typescript';
    case 'js':
    case 'jsx':
      return 'javascript';
    case 'json':
      return 'json';
    case 'yml':
    case 'yaml':
      return 'yaml';
    case 'md':
      return 'markdown';
    case 'sh':
    case 'bash':
      return 'bash';
    case 'css':
      return 'css';
    case 'html':
      return 'html';
    case 'sql':
      return 'sql';
    case 'toml':
      return 'toml';
    default:
      return ext;
  }
}

export interface FileDiffBlockProps {
  diffOrContent: string;
  maxLines?: number;
  language?: string;
  title?: string;
  isNewFile?: boolean;
}

function renderLine(
  line: DiffLine,
  index: number,
  theme: Theme,
  language: string | undefined,
  maskFor: (index: number, type: DiffLine['type']) => boolean[] | undefined,
  hasBoth: boolean,
  isUnifiedDiff: boolean,
): React.ReactNode {
  if (line.type === 'hunk') {
    // Hide @@ -14,15 +12,12 @@ hunk headers; colored diff and line numbers display changes cleanly
    return null;
  }

  const isAdd = line.type === 'add';
  const isDelete = line.type === 'delete';

  // In Git Diff mode, added/deleted lines get row background fills.
  // In Plain Code mode (new file creation), lines get standard code background without patch fills.
  const rowBackground = isUnifiedDiff
    ? isAdd
      ? theme.colors.diff.addBg
      : isDelete
        ? theme.colors.diff.removeBg
        : undefined
    : undefined;

  const changedFg = isUnifiedDiff
    ? isAdd
      ? theme.colors.status.success
      : isDelete
        ? theme.colors.status.error
        : undefined
    : undefined;

  const changedBg = isUnifiedDiff
    ? isAdd
      ? theme.colors.diff.addWordBg
      : isDelete
        ? theme.colors.diff.removeWordBg
        : undefined
    : undefined;

  const colors = charColors(line.content, theme, language);
  const mask = maskFor(index, line.type);

  return (
    <Box key={index} flexDirection="row" width="100%" backgroundColor={rowBackground}>
      {renderGutter(line, theme, isAdd, isDelete, hasBoth, isUnifiedDiff)}
      <Box flexGrow={1} flexShrink={1}>
        <Text wrap="truncate-end">
          {contentNodes(
            line.content,
            colors,
            isUnifiedDiff && (isAdd || isDelete) ? mask : undefined,
            changedFg,
            changedBg,
          )}
        </Text>
      </Box>
    </Box>
  );
}

export const FileDiffBlock: React.FC<FileDiffBlockProps> = React.memo(
  ({ diffOrContent, maxLines = 30, language, title }) => {
    const { theme } = useTheme();
    const { lines, isUnifiedDiff } = parseDiffOrContent(diffOrContent, maxLines);

    if (lines.length === 0) return null;

    const effectiveLang = language || detectLanguageFromFilename(title);
    const hasBoth = lines.some((l) => l.oldLineNumber !== undefined && l.newLineNumber !== undefined);

    const changedMasks = new Map<number, boolean[]>();
    if (isUnifiedDiff) {
      for (let index = 0; index < lines.length; index++) {
        const line = lines[index];
        if (line.type === 'add' && index > 0 && lines[index - 1].type === 'delete') {
          const prev = lines[index - 1];
          const { removedFlags, addedFlags } = diffMasks(tokenize(prev.content), tokenize(line.content));
          changedMasks.set(index - 1, tokenFlagsToCharMask(prev.content, removedFlags));
          changedMasks.set(index, tokenFlagsToCharMask(line.content, addedFlags));
        }
      }
    }

    const maskFor = (index: number, _type: DiffLine['type']): boolean[] | undefined => {
      return changedMasks.get(index);
    };

    const isAllAdd = lines.length > 0 && lines.every((l) => l.type === 'add');
    const containerBg = isAllAdd ? theme.colors.diff.addBg : theme.colors.code.background;

    return (
      <Box flexDirection="column" width="100%" marginTop={0} marginBottom={1}>
        {/* Unified Diff & File View Container with top and bottom padding */}
        <Box flexDirection="column" width="100%" paddingY={1} backgroundColor={containerBg}>
          {lines.map((line, index) => renderLine(line, index, theme, effectiveLang, maskFor, hasBoth, isUnifiedDiff))}
        </Box>
      </Box>
    );
  },
);

FileDiffBlock.displayName = 'FileDiffBlock';
