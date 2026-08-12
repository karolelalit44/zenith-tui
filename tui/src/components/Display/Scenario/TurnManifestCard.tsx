import { Box, Text } from 'ink';
import React from 'react';
import { useTheme } from '../../../theme/ThemeContext';
import type { TurnManifestEvent } from '../../../types/scenario';
import { formatBytes } from '../../../utils/text';

interface TurnManifestCardProps {
  event: TurnManifestEvent;
}

const MAX_FILES = 8;

export function formatTurnSummary(event: TurnManifestEvent): string {
  if (event.created.length === 0 && event.modified.length === 0 && event.remaining.length === 0) {
    return 'no changes';
  }
  const parts: string[] = [];
  if (event.created.length > 0) parts.push(`${event.created.length} created`);
  if (event.modified.length > 0) parts.push(`${event.modified.length} modified`);
  if (event.completed) {
    parts.push('complete');
  } else {
    parts.push(`${event.remaining.length} remaining`);
  }
  return parts.join(' · ');
}

interface TreeFile {
  path: string;
  size?: number;
  kind: 'created' | 'modified';
}

interface TreeNode {
  name: string;
  children: Map<string, TreeNode>;
  file?: TreeFile;
}

/** Build a nested directory tree from relative file paths. */
function buildTree(files: TreeFile[]): TreeNode {
  const root: TreeNode = { name: '', children: new Map() };
  for (const file of files) {
    const segments = file.path.split(/[\\/]+/).filter(Boolean);
    let node = root;
    for (let index = 0; index < segments.length; index++) {
      const segment = segments[index];
      let child = node.children.get(segment);
      if (!child) {
        child = { name: segment, children: new Map() };
        node.children.set(segment, child);
      }
      if (index === segments.length - 1) child.file = file;
      node = child;
    }
  }
  return root;
}

const KIND_ICON: Record<
  TreeFile['kind'],
  { icon: string; color: (t: ReturnType<typeof useTheme>['theme']) => string }
> = {
  created: { icon: '+ ', color: (t) => t.colors.status.success },
  modified: { icon: '✎ ', color: (t) => t.colors.status.info },
};

/** Render a directory tree with branch connectors and right-aligned sizes. */
function renderChildren(
  node: TreeNode,
  prefix: string,
  theme: ReturnType<typeof useTheme>['theme'],
): React.ReactNode[] {
  const children = [...node.children.values()];
  const out: React.ReactNode[] = [];
  children.forEach((child, index) => {
    const isLast = index === children.length - 1;
    const branch = isLast ? '└── ' : '├── ';
    const line = `${prefix}${branch}`;

    if (child.children.size > 0) {
      out.push(
        <Box key={`dir-${child.name}`} flexDirection="row" width="100%">
          <Text color={theme.colors.text.bright} bold wrap="truncate-end">
            {line}
            {child.name}/
          </Text>
        </Box>,
      );
    } else {
      const style = KIND_ICON[child.file?.kind ?? 'modified'];
      out.push(
        <Box key={`file-${child.name}`} flexDirection="row" justifyContent="space-between" width="100%">
          <Text color={style.color(theme)} wrap="truncate-end">
            {line}
            {style.icon}
            {child.name}
          </Text>
          {typeof child.file?.size === 'number' && child.file.size >= 0 ? (
            <Text color={theme.colors.text.dim}> {formatBytes(child.file.size)}</Text>
          ) : null}
        </Box>,
      );
    }

    out.push(...renderChildren(child, `${prefix}${isLast ? '    ' : '│   '}`, theme));
  });
  return out;
}

export const TurnManifestCard: React.FC<TurnManifestCardProps> = React.memo(({ event }) => {
  const { theme } = useTheme();

  const fileEntries: TreeFile[] = [
    ...event.files
      .filter((f) => event.created.includes(f.path))
      .map((f) => ({ path: f.path, size: f.size, kind: 'created' as const })),
    ...event.modified.map((path) => ({ path, kind: 'modified' as const })),
  ];
  const shown = fileEntries.slice(0, MAX_FILES);
  const hidden = fileEntries.length - shown.length;
  const tree = buildTree(shown);

  return (
    <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
      <Box flexDirection="row" alignItems="center">
        <Text
          color={
            event.completed
              ? theme.colors.status.success
              : event.stalled
                ? theme.colors.status.warning
                : theme.colors.status.info
          }
          bold
        >
          {event.completed ? '✓ Turn complete' : event.stalled ? '● Turn stalled' : '⧗ Turn paused'}
        </Text>
        <Text color={theme.colors.text.muted}> </Text>
        <Text color={theme.colors.text.muted}>{formatTurnSummary(event)}</Text>
      </Box>

      {(event.created.length > 0 || event.modified.length > 0) && (
        <Box flexDirection="column" paddingLeft={1} width="100%">
          {renderChildren(tree, '', theme)}
          {hidden > 0 && (
            <Box paddingLeft={2}>
              <Text color={theme.colors.text.muted}>… {hidden} more</Text>
            </Box>
          )}
        </Box>
      )}

      {event.remaining.length > 0 && (
        <Box flexDirection="column" paddingLeft={1} paddingTop={1} width="100%">
          <Box flexDirection="row">
            <Box width={2}>
              <Text color={theme.colors.status.warning}>◈</Text>
            </Box>
            <Text color={theme.colors.text.bright} bold>
              Remaining
            </Text>
          </Box>
          {event.remaining.slice(0, MAX_FILES).map((item, idx) => (
            <Box key={idx} paddingLeft={2}>
              <Text color={theme.colors.text.muted}>- {item}</Text>
            </Box>
          ))}
          {event.remaining.length > MAX_FILES && (
            <Box paddingLeft={2}>
              <Text color={theme.colors.text.muted}>… {event.remaining.length - MAX_FILES} more</Text>
            </Box>
          )}
        </Box>
      )}
    </Box>
  );
});
