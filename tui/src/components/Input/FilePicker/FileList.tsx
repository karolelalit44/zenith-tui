import { Box, Text } from 'ink';
import React from 'react';
import { useTerminalDimensions } from '../../../hooks/useTerminalDimensions';
import type { FileNode } from '../../../services/fileExplorer';
import { useTheme } from '../../../theme/ThemeContext';

interface FileListLayout {
  name: number;
  size: number;
  modified: number;
  kind: number;
}

export function getFileListLayout(columns: number): FileListLayout {
  const innerWidth = Math.max(12, (columns || 80) - 10);
  if (innerWidth < 42) {
    return { name: Math.max(8, innerWidth - 2), size: 0, modified: 0, kind: 0 };
  }
  if (innerWidth < 58) {
    return { name: Math.max(12, innerWidth - 10), size: 8, modified: 0, kind: 0 };
  }
  return {
    name: Math.max(16, innerWidth - 36),
    size: 10,
    modified: 14,
    kind: 10,
  };
}

interface FileListProps {
  items: FileNode[];
  activeIndex: number;
  currentPath: string;
}

export const FileList: React.FC<FileListProps> = React.memo(({ items, activeIndex, currentPath }) => {
  const { theme } = useTheme();
  const { columns } = useTerminalDimensions();
  const layout = getFileListLayout(columns || process.stdout.columns || 80);

  if (items.length === 0) {
    return (
      <Box paddingY={1}>
        <Text color={theme.colors.text.muted}>No files or folders found in {currentPath || 'workspace'}.</Text>
      </Box>
    );
  }

  return (
    <Box flexDirection="column" width="100%">
      {items.map((item, idx) => {
        const isActive = idx === activeIndex;

        return (
          <Box key={item.relativePath} flexDirection="row" alignItems="center" width="100%">
            <Box width={2} flexShrink={0}>
              <Text color={isActive ? theme.colors.status.success : theme.colors.text.muted}>
                {isActive ? '▸' : ' '}
              </Text>
            </Box>

            <Box width={layout.name} flexShrink={1} flexGrow={1}>
              <Text
                color={
                  isActive
                    ? theme.colors.text.bright
                    : item.name === '..'
                      ? theme.colors.text.dim
                      : item.isDir
                        ? theme.colors.status.info
                        : theme.colors.code.output
                }
                bold={isActive || item.isDir}
                wrap="truncate-end"
              >
                {item.name === '..' ? '..' : item.isDir ? `${item.name}/` : item.name}
              </Text>
            </Box>

            {layout.size > 0 ? (
              <Box width={layout.size} flexShrink={0}>
                <Text color={theme.colors.text.muted}>{item.isDir ? '—' : item.sizeFormatted || '0 KB'}</Text>
              </Box>
            ) : null}

            {layout.modified > 0 ? (
              <Box width={layout.modified} flexShrink={0}>
                <Text color={theme.colors.text.muted}>{item.modifiedDate || '—'}</Text>
              </Box>
            ) : null}

            {layout.kind > 0 ? (
              <Box width={layout.kind} flexShrink={0}>
                <Text color={theme.colors.text.muted} wrap="truncate-end">
                  {item.name === '..' ? '' : item.fileType || (item.isDir ? 'Folder' : 'File')}
                </Text>
              </Box>
            ) : null}
          </Box>
        );
      })}
    </Box>
  );
});
