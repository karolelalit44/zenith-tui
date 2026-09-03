import { Box, Text, useInput } from 'ink';
import React, { useEffect, useMemo, useState } from 'react';
import { type FileNode, getDirectoryContents, searchFiles } from '../../../services/fileExplorer';
import { useTheme } from '../../../theme/ThemeContext';
import { FileList } from './FileList';

interface FilePickerModalProps {
  onSelectFile: (relativePath: string, kind: 'file' | 'folder') => void;
  onClose: () => void;
  /** Initial directory to browse ('' = workspace root). */
  initialPath?: string;
  /** Initial filter seed (mid-text @ prefix). */
  initialQuery?: string;
}

export const FilePickerModal: React.FC<FilePickerModalProps> = ({
  onSelectFile,
  onClose,
  initialPath = '',
  initialQuery = '',
}) => {
  const { theme } = useTheme();
  const PAGE_SIZE = 15;
  const [currentPath, setCurrentPath] = useState(initialPath);
  const [searchQuery, setSearchQuery] = useState(initialQuery);
  const [activeIndex, setActiveIndex] = useState(0);
  const [scrollOffset, setScrollOffset] = useState(0);

  useEffect(() => {
    setCurrentPath(initialPath);
    setSearchQuery(initialQuery);
    setActiveIndex(0);
    setScrollOffset(0);
  }, [initialPath, initialQuery]);

  const items: FileNode[] = useMemo(() => {
    if (searchQuery.trim()) {
      return searchFiles(searchQuery);
    }
    return getDirectoryContents(currentPath);
  }, [currentPath, searchQuery]);

  useEffect(() => {
    if (activeIndex < scrollOffset) {
      setScrollOffset(activeIndex);
    } else if (activeIndex >= scrollOffset + PAGE_SIZE) {
      setScrollOffset(activeIndex - PAGE_SIZE + 1);
    }
  }, [activeIndex, scrollOffset]);

  const visibleItems = useMemo(() => {
    return items.slice(scrollOffset, scrollOffset + PAGE_SIZE);
  }, [items, scrollOffset]);

  useInput((char, key) => {
    if (key.escape) {
      onClose();
      return;
    }

    if (key.upArrow) {
      setActiveIndex((prev) => Math.max(0, prev - 1));
      return;
    }

    if (key.downArrow) {
      setActiveIndex((prev) => Math.min(items.length - 1, prev + 1));
      return;
    }

    const selectedItem = items[activeIndex];

    if (selectedItem?.name === '..') {
      if (key.return || key.rightArrow || key.leftArrow) {
        setCurrentPath(selectedItem.relativePath);
        setActiveIndex(0);
        setScrollOffset(0);
        setSearchQuery('');
        return;
      }
    }

    if ((key.rightArrow || key.return) && selectedItem?.isDir) {
      setCurrentPath(selectedItem.relativePath);
      setActiveIndex(0);
      setScrollOffset(0);
      setSearchQuery('');
      return;
    }

    if (key.leftArrow) {
      if (currentPath) {
        const parts = currentPath.split('/').filter(Boolean);
        parts.pop();
        setCurrentPath(parts.join('/'));
        setActiveIndex(0);
        setScrollOffset(0);
        setSearchQuery('');
      } else {
        onClose();
      }
      return;
    }

    // Enter on a file selects and attaches the file directly
    if (key.return && selectedItem && !selectedItem.isDir) {
      onSelectFile(selectedItem.relativePath, 'file');
      onClose();
      return;
    }

    // Select a folder without navigating into it
    if ((key.ctrl || key.meta) && (char === ' ' || char === 's' || char === 'S')) {
      if (selectedItem?.isDir && selectedItem.name !== '..') {
        onSelectFile(selectedItem.relativePath, 'folder');
        onClose();
      }
      return;
    }

    if (char && !key.ctrl && !key.meta && char.length === 1) {
      const sanitized = char.replace(/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/g, '');
      if (sanitized) {
        setSearchQuery((prev) => prev + sanitized);
        setActiveIndex(0);
        setScrollOffset(0);
      }
    } else if (key.backspace || key.delete) {
      setSearchQuery((prev) => prev.slice(0, -1));
      setActiveIndex(0);
      setScrollOffset(0);
    }
  });

  return (
    <Box
      flexDirection="column"
      width="100%"
      borderStyle="round"
      borderColor={theme.colors.status.info}
      paddingX={1}
      paddingY={1}
      marginTop={1}
    >
      <Box flexDirection="row" justifyContent="space-between" alignItems="center" marginBottom={1}>
        <Box flexDirection="row" alignItems="center">
          <Text color={theme.colors.text.bright} bold>
            {currentPath ? `./${currentPath}/` : './'}
          </Text>
        </Box>
        <Box flexDirection="row" alignItems="center">
          {searchQuery ? (
            <>
              <Text color={theme.colors.text.muted}>search: </Text>
              <Text color={theme.colors.status.success} bold>
                {searchQuery}
              </Text>
              <Text color={theme.colors.text.bright}>_</Text>
            </>
          ) : (
            <Text color={theme.colors.text.dim} italic>
              Type to search...
            </Text>
          )}
        </Box>
      </Box>

      <Box flexDirection="row" marginBottom={1}>
        <Box width={2} flexShrink={0} />
        <Box width={30} flexShrink={0}>
          <Text color={theme.colors.text.muted} bold>
            NAME
          </Text>
        </Box>
        <Box width={10} flexShrink={0}>
          <Text color={theme.colors.text.muted} bold>
            SIZE
          </Text>
        </Box>
        <Box width={14} flexShrink={0}>
          <Text color={theme.colors.text.muted} bold>
            MODIFIED
          </Text>
        </Box>
        <Box flexShrink={1}>
          <Text color={theme.colors.text.muted} bold>
            KIND
          </Text>
        </Box>
      </Box>

      <FileList items={visibleItems} activeIndex={activeIndex - scrollOffset} currentPath={currentPath} />

      {items.length > PAGE_SIZE && (
        <Box flexDirection="row" justifyContent="space-between" alignItems="center" marginTop={1} paddingX={1}>
          <Text color={theme.colors.text.dim}>{scrollOffset > 0 ? '↑ more above' : ' '}</Text>
          <Text color={theme.colors.text.muted}>
            {activeIndex + 1} / {items.length}
          </Text>
          <Text color={theme.colors.text.dim}>{scrollOffset + PAGE_SIZE < items.length ? '↓ more below' : ' '}</Text>
        </Box>
      )}
    </Box>
  );
};
