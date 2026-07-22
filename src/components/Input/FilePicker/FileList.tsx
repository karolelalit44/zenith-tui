import { Box, Text } from 'ink';
import React from 'react';
import type { FileNode } from '../../../services/fileExplorerService';
import { useTheme } from '../../../theme/ThemeContext';

interface FileListProps {
  items: FileNode[];
  activeIndex: number;
  currentPath: string;
}

export const FileList: React.FC<FileListProps> = React.memo(({ items, activeIndex, currentPath }) => {
  const { theme } = useTheme();

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

            <Box width={7} flexShrink={0}>
              <Text color={item.isDir ? theme.colors.status.info : theme.colors.status.success} bold={item.isDir}>
                {item.isDir ? '[DIR]' : '[FILE]'}
              </Text>
            </Box>

            <Box width={24} flexShrink={0}>
              <Text
                color={
                  isActive ? theme.colors.text.bright : item.isDir ? theme.colors.status.info : theme.colors.code.output
                }
                bold={isActive || item.isDir}
                wrap="truncate-end"
              >
                {item.name}
              </Text>
            </Box>

            <Box width={10} flexShrink={0}>
              <Text color={theme.colors.text.muted}>{item.isDir ? '—' : item.sizeFormatted || '0 KB'}</Text>
            </Box>

            <Box width={14} flexShrink={0}>
              <Text color={theme.colors.text.muted}>{item.modifiedDate || 'Jul 22, 2026'}</Text>
            </Box>

            <Box flexShrink={1}>
              <Text color={theme.colors.text.muted}>{item.fileType || (item.isDir ? 'Folder' : 'File')}</Text>
            </Box>
          </Box>
        );
      })}
    </Box>
  );
});
