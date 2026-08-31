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
  const [currentPath, setCurrentPath] = useState(initialPath);
  const [searchQuery, setSearchQuery] = useState(initialQuery);
  const [activeIndex, setActiveIndex] = useState(0);

  useEffect(() => {
    setCurrentPath(initialPath);
    setSearchQuery(initialQuery);
    setActiveIndex(0);
  }, [initialPath, initialQuery]);

  const items: FileNode[] = useMemo(() => {
    if (searchQuery.trim()) {
      return searchFiles(searchQuery);
    }
    return getDirectoryContents(currentPath);
  }, [currentPath, searchQuery]);

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

    if ((key.rightArrow || key.return) && selectedItem?.isDir) {
      setCurrentPath(selectedItem.relativePath);
      setActiveIndex(0);
      setSearchQuery('');
      return;
    }

    if (key.leftArrow) {
      if (currentPath) {
        const parts = currentPath.split('/');
        parts.pop();
        setCurrentPath(parts.join('/'));
        setActiveIndex(0);
        setSearchQuery('');
      } else {
        onClose();
      }
      return;
    }

    // Enter on a file selects the file; ctrl+space/alt on a dir selects the folder.
    if (key.return && selectedItem && !selectedItem.isDir) {
      onSelectFile(selectedItem.relativePath, 'file');
      onClose();
      return;
    }

    // Select a folder (scope reference) without navigating into it.
    if ((key.ctrl || key.meta) && (char === ' ' || char === 's' || char === 'S')) {
      if (selectedItem?.isDir) {
        onSelectFile(selectedItem.relativePath, 'folder');
        onClose();
      }
      return;
    }

    if (char && !key.ctrl && !key.meta && char.length === 1) {
      const sanitized = char.replace(/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/g, '');
      if (sanitized) setSearchQuery((prev) => prev + sanitized);
      setActiveIndex(0);
    } else if (key.backspace || key.delete) {
      setSearchQuery((prev) => prev.slice(0, -1));
      setActiveIndex(0);
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
          <Text color={theme.colors.status.info} bold>
            [FILE EXPLORER]{' '}
          </Text>
          <Text color={theme.colors.text.bright} bold>
            {currentPath ? `./${currentPath}` : './ (workspace root)'}
          </Text>
        </Box>
        <Text color={theme.colors.text.muted}>↑/↓ · →/Enter in · ←/Esc · Ctrl+Space select dir</Text>
      </Box>

      {searchQuery && (
        <Box flexDirection="row" marginBottom={1}>
          <Text color={theme.colors.text.muted}>Search filter: </Text>
          <Text color={theme.colors.status.success} bold>
            {searchQuery}
          </Text>
        </Box>
      )}

      <Box flexDirection="row" marginBottom={1} borderStyle="single" borderColor={theme.colors.code.border}>
        <Box width={2} flexShrink={0} />
        <Box width={7} flexShrink={0}>
          <Text color={theme.colors.text.muted} bold>
            TYPE
          </Text>
        </Box>
        <Box width={24} flexShrink={0}>
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

      <FileList items={items} activeIndex={activeIndex} currentPath={currentPath} />

      {/* Hint for folder selection */}
      {items[activeIndex]?.isDir && (
        <Box marginTop={1}>
          <Text color={theme.colors.text.dim}>
            Press{' '}
            <Text color={theme.colors.status.info} bold>
              Ctrl+Space
            </Text>{' '}
            to attach folder{' '}
            <Text color={theme.colors.text.bright} bold>
              {items[activeIndex]?.name}/
            </Text>
          </Text>
        </Box>
      )}
    </Box>
  );
};
