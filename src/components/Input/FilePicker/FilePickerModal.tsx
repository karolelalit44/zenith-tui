import { Box, Text, useInput } from 'ink';
import React, { useMemo, useState } from 'react';
import { type FileNode, getDirectoryContents, searchFiles } from '../../../services/fileExplorerService';
import { useTheme } from '../../../theme/ThemeContext';
import { FileList } from './FileList';

interface FilePickerModalProps {
  onSelectFile: (relativePath: string) => void;
  onClose: () => void;
}

export const FilePickerModal: React.FC<FilePickerModalProps> = ({ onSelectFile, onClose }) => {
  const { theme } = useTheme();
  const [currentPath, setCurrentPath] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [activeIndex, setActiveIndex] = useState(0);

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

    if (key.return && selectedItem && !selectedItem.isDir) {
      onSelectFile(selectedItem.relativePath);
      onClose();
      return;
    }

    if (char && !key.ctrl && !key.meta && char.length === 1) {
      setSearchQuery((prev) => prev + char);
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
        <Text color={theme.colors.text.muted}>↑/↓ navigate · →/Enter enter · ← back · Esc exit</Text>
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
        <Box width={9}>
          <Text color={theme.colors.text.muted} bold>
            {' '}
            TYPE
          </Text>
        </Box>
        <Box width={24}>
          <Text color={theme.colors.text.muted} bold>
            NAME
          </Text>
        </Box>
        <Box width={10}>
          <Text color={theme.colors.text.muted} bold>
            SIZE
          </Text>
        </Box>
        <Box width={14}>
          <Text color={theme.colors.text.muted} bold>
            MODIFIED
          </Text>
        </Box>
        <Box>
          <Text color={theme.colors.text.muted} bold>
            KIND
          </Text>
        </Box>
      </Box>

      <FileList items={items} activeIndex={activeIndex} currentPath={currentPath} />
    </Box>
  );
};
