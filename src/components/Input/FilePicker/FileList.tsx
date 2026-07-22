import React from 'react';
import { Box, Text } from 'ink';
import { useTheme } from '../../../theme/ThemeContext';
import { FileNode } from '../../../services/fileExplorerService';

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
        <Text color="#8B949E">No files or folders found in {currentPath || 'workspace'}.</Text>
      </Box>
    );
  }

  return (
    <Box flexDirection="column" width="100%">
      {items.map((item, idx) => {
        const isActive = idx === activeIndex;

        return (
          <Box key={item.relativePath} flexDirection="row" alignItems="center" width="100%">
            {/* Active Pointer */}
            <Box width={2} flexShrink={0}>
              <Text color={isActive ? "#3FB950" : theme.colors.text.muted}>
                {isActive ? '▸' : ' '}
              </Text>
            </Box>

            {/* Type Indicator Badge */}
            <Box width={7} flexShrink={0}>
              <Text color={item.isDir ? "#58A6FF" : "#3FB950"} bold={item.isDir}>
                {item.isDir ? '[DIR]' : '[FILE]'}
              </Text>
            </Box>

            {/* Name */}
            <Box width={24} flexShrink={0}>
              <Text
                color={isActive ? "#E6EDF3" : item.isDir ? "#58A6FF" : "#C9D1D9"}
                bold={isActive || item.isDir}
                wrap="truncate-end"
              >
                {item.name}
              </Text>
            </Box>

            {/* Size */}
            <Box width={10} flexShrink={0}>
              <Text color="#8B949E">
                {item.isDir ? '—' : (item.sizeFormatted || '0 KB')}
              </Text>
            </Box>

            {/* Modified Date */}
            <Box width={14} flexShrink={0}>
              <Text color="#8B949E">
                {item.modifiedDate || 'Jul 22, 2026'}
              </Text>
            </Box>

            {/* File Type */}
            <Box flexShrink={1}>
              <Text color="#8B949E">
                {item.fileType || (item.isDir ? 'Folder' : 'File')}
              </Text>
            </Box>
          </Box>
        );
      })}
    </Box>
  );
});
