import { Box, Text } from 'ink';
import React from 'react';
import { useTheme } from '../../../theme/ThemeContext';
import type { Theme } from '../../../theme/theme';
import { highlightCode } from '../../../utils/syntaxHighlight';

/** Fixed gutter column width reserved for the dual line numbers. */
const GUTTER_WIDTH = 4;

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

/**
 * Longest-common-subsequence mask between two token arrays: one flag per token
 * in each input marking which tokens are unique to that side (removed/added).
 * Common (unchanged) tokens are flagged false so they keep their syntax color.
 * Generic — derived from the actual line pair, never hardcoded to any content.
 */
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

/** Expand per-token flags into a per-character "changed" mask for `content`. */
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

/** Per-character syntax color for `content`, resolved from the active theme. */
function charColors(content: string, theme: Theme, language?: string): string[] {
  const colors = new Array<string>(content.length).fill(theme.colors.text.ethereal);
  let pos = 0;
  for (const seg of highlightCode(content, theme, language)) {
    for (let c = pos; c < pos + seg.text.length && c < content.length; c++) colors[c] = seg.color;
    pos += seg.text.length;
  }
  return colors;
}

/**
 * Render `content` as grouped ink text runs (grouped by color + changed flag).
 * Changed characters get an explicit word-level background and diff foreground;
 * unchanged characters retain their syntax color on the (row-level) line fill.
 */
function contentNodes(
  content: string,
  colors: string[],
  mask: boolean[] | undefined,
  changedFg: string,
  changedBg: string,
): React.ReactNode[] {
  const length = Math.min(content.length, colors.length);
  const changedMask = mask ?? new Array<boolean>(length).fill(false);
  const nodes: React.ReactNode[] = [];
  let index = 0;
  while (index < length) {
    const changed = changedMask[index];
    const color = changed ? changedFg : colors[index];
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

/** Render a single diff gutter: `[old] ⋮ [new] │`. */
function renderGutter(line: DiffLine, theme: Theme, changedFg: string, isAdd: boolean, isDelete: boolean) {
  const width = GUTTER_WIDTH;
  const fill = (num: number | undefined, color: string) => (
    <Text color={num === undefined ? theme.colors.code.lineNum : color}>
      {num === undefined ? ''.padStart(width) : String(num).padStart(width)}
    </Text>
  );
  return (
    <>
      {fill(line.oldLineNumber, isDelete ? changedFg : theme.colors.code.lineNum)}
      <Text color={theme.colors.text.dim}>⋮</Text>
      {fill(line.newLineNumber, isAdd ? changedFg : theme.colors.code.lineNum)}
      <Text color={theme.colors.border.default}>│</Text>
      <Text color={changedFg}>{(isAdd ? '+' : isDelete ? '-' : ' ').padEnd(2)}</Text>
    </>
  );
}

export function parseDiffOrContent(text: string, maxLines = 25): DiffLine[] {
  if (!text?.trim()) return [];

  const lines = text.split('\n');
  // A trailing newline is file-content noise, not an empty diff line.
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
      // Raw content for newly created files
      result.push({
        type: 'add',
        newLineNumber: curNew++,
        content: line,
      });
    }
  }

  return result;
}

export interface FileDiffBlockProps {
  diffOrContent: string;
  maxLines?: number;
  language?: string;
  title?: string;
}

function renderDiffLine(
  line: DiffLine,
  index: number,
  theme: Theme,
  language: string | undefined,
  maskFor: (index: number, type: DiffLine['type']) => boolean[] | undefined,
): React.ReactNode {
  if (line.type === 'hunk') {
    return (
      <Box key={index} flexDirection="column" width="100%" marginBottom={1}>
        <Box borderStyle="single" borderColor={theme.colors.status.warning} paddingX={1} paddingY={0}>
          <Text color={theme.colors.status.warning} wrap="truncate-end">
            {line.content}
          </Text>
        </Box>
      </Box>
    );
  }

  const isAdd = line.type === 'add';
  const isDelete = line.type === 'delete';
  const rowBackground = isAdd ? theme.colors.diff.addBg : isDelete ? theme.colors.diff.removeBg : undefined;
  const changedFg = isAdd ? theme.colors.diff.addFg : theme.colors.diff.removeFg;
  const changedBg = isAdd ? theme.colors.diff.addWordBg : theme.colors.diff.removeWordBg;

  const colors = charColors(line.content, theme, language);
  const mask = maskFor(index, line.type);

  return (
    <Box key={index} flexDirection="row" width="100%" backgroundColor={rowBackground}>
      {renderGutter(line, theme, changedFg, isAdd, isDelete)}
      <Box flexGrow={1} flexShrink={1}>
        <Text wrap="truncate-end">
          {contentNodes(line.content, colors, isAdd || isDelete ? mask : undefined, changedFg, changedBg)}
        </Text>
      </Box>
    </Box>
  );
}

export const FileDiffBlock: React.FC<FileDiffBlockProps> = React.memo(
  ({ diffOrContent, maxLines = 25, language, title }) => {
    const { theme } = useTheme();
    const lines = parseDiffOrContent(diffOrContent, maxLines);

    if (lines.length === 0) return null;

    const addedCount = lines.filter((l) => l.type === 'add').length;
    const deletedCount = lines.filter((l) => l.type === 'delete').length;

    // Pair each deleted line with the added line that immediately follows it to
    // compute word-level (intra-line) highlights for that replacement.
    const changedMasks = new Map<number, boolean[]>();
    for (let index = 0; index < lines.length; index++) {
      const line = lines[index];
      if (line.type === 'add' && index > 0 && lines[index - 1].type === 'delete') {
        const prev = lines[index - 1];
        const { removedFlags, addedFlags } = diffMasks(tokenize(prev.content), tokenize(line.content));
        changedMasks.set(index - 1, tokenFlagsToCharMask(prev.content, removedFlags));
        changedMasks.set(index, tokenFlagsToCharMask(line.content, addedFlags));
      }
    }

    const maskFor = (index: number, _type: DiffLine['type']): boolean[] | undefined => {
      // Word-level highlights apply ONLY to a line that participates in a
      // paired add/delete replacement. A purely new file (no deletions) or an
      // unpaired whole-line edit keeps its syntax colors on the full-line fill
      // instead of becoming a solid word-highlighted "hot spot".
      return changedMasks.get(index);
    };

    const ruleWidth = Math.max(16, (process.stdout.columns ?? 80) - 8);

    return (
      <Box flexDirection="column" width="100%" paddingLeft={2}>
        <Box
          flexDirection="column"
          backgroundColor={theme.colors.code.background}
          borderStyle="single"
          borderColor={theme.colors.border.muted}
          paddingX={1}
          paddingY={0}
        >
          {title ? (
            <Box flexDirection="column" marginBottom={1}>
              <Box flexDirection="row" alignItems="center" width="100%">
                <Box flexGrow={0} flexShrink={1}>
                  <Text color={theme.colors.status.warning} bold underline wrap="truncate-end">
                    {title}
                  </Text>
                </Box>
                <Box flexGrow={1} flexShrink={1} />
                <Box flexGrow={0} flexShrink={0}>
                  <Text color={theme.colors.text.dim}>
                    {addedCount > 0 && <Text color={theme.colors.status.success}>+{addedCount} </Text>}
                    {deletedCount > 0 && <Text color={theme.colors.status.error}>-{deletedCount} </Text>}
                    lines
                  </Text>
                </Box>
              </Box>
              <Text color={theme.colors.border.muted}>{'─'.repeat(ruleWidth)}</Text>
            </Box>
          ) : null}

          {lines.map((line, index) => renderDiffLine(line, index, theme, language, maskFor))}
        </Box>
      </Box>
    );
  },
);

FileDiffBlock.displayName = 'FileDiffBlock';
