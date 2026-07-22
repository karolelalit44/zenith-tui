import React, { useState, useMemo } from 'react';
import { Box, Text, useInput } from 'ink';
import { useTheme } from '../../../theme/ThemeContext';
import { FileList } from './FileList';
import { getDirectoryContents, searchFiles, FileNode } from '../../../services/fileExplorerService';

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
      setActiveIndex(prev => Math.max(0, prev - 1));
      return;
    }

    if (key.downArrow) {
      setActiveIndex(prev => Math.min(items.length - 1, prev + 1));
      return;
    }

    const selectedItem = items[activeIndex];

    // Right Arrow or Enter on directory -> Enter folder
    if ((key.rightArrow || key.return) && selectedItem?.isDir) {
      setCurrentPath(selectedItem.relativePath);
      setActiveIndex(0);
      setSearchQuery('');
      return;
    }

    // Left Arrow -> Parent directory
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

    // Enter on file -> Select & return relative path
    if (key.return && selectedItem && !selectedItem.isDir) {
      onSelectFile(selectedItem.relativePath);
      onClose();
      return;
    }

    // Typing query to filter files
    if (char && !key.ctrl && !key.meta && char.length === 1) {
      setSearchQuery(prev => prev + char);
      setActiveIndex(0);
    } else if (key.backspace || key.delete) {
      setSearchQuery(prev => prev.slice(0, -1));
      setActiveIndex(0);
    }
  });

  return (
    <Box flexDirection="column" width="100%" borderStyle="round" borderColor="#58A6FF" paddingX={1} paddingY={1} marginTop={1}>
      {/* Header bar */}
      <Box flexDirection="row" justifyContent="space-between" alignItems="center" marginBottom={1}>
        <Box flexDirection="row" alignItems="center">
          <Text color="#58A6FF" bold>[FILE EXPLORER] </Text>
          <Text color="#E6EDF3" bold>
            {currentPath ? `./${currentPath}` : './ (workspace root)'}
          </Text>
        </Box>
        <Text color="#8B949E">
          ↑/↓ navigate · →/Enter enter · ← back · Esc exit
        </Text>
      </Box>

      {/* Search Input Bar if searching */}
      {searchQuery && (
        <Box flexDirection="row" marginBottom={1}>
          <Text color="#8B949E">Search filter: </Text>
          <Text color="#3FB950" bold>{searchQuery}</Text>
        </Box>
      )}

      {/* Table Header */}
      <Box flexDirection="row" marginBottom={1} borderStyle="single" borderColor="#30363D">
        <Box width={9}><Text color="#8B949E" bold> TYPE</Text></Box>
        <Box width={24}><Text color="#8B949E" bold>NAME</Text></Box>
        <Box width={10}><Text color="#8B949E" bold>SIZE</Text></Box>
        <Box width={14}><Text color="#8B949E" bold>MODIFIED</Text></Box>
        <Box><Text color="#8B949E" bold>KIND</Text></Box>
      </Box>

      {/* File List Table */}
      <FileList items={items} activeIndex={activeIndex} currentPath={currentPath} />
    </Box>
  );
};
