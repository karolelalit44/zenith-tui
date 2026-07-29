import { Box, Text, useInput } from 'ink';
import React, { useMemo, useState } from 'react';
import { getDirectoryContents, searchFiles } from '../../../services/fileExplorerService';
import { useTheme } from '../../../theme/ThemeContext';
import { FileList } from './FileList';
export const FilePickerModal = ({ onSelectFile, onClose }) => {
    const { theme } = useTheme();
    const [currentPath, setCurrentPath] = useState('');
    const [searchQuery, setSearchQuery] = useState('');
    const [activeIndex, setActiveIndex] = useState(0);
    const items = useMemo(() => {
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
            }
            else {
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
        }
        else if (key.backspace || key.delete) {
            setSearchQuery((prev) => prev.slice(0, -1));
            setActiveIndex(0);
        }
    });
    return (React.createElement(Box, { flexDirection: "column", width: "100%", borderStyle: "round", borderColor: theme.colors.status.info, paddingX: 1, paddingY: 1, marginTop: 1 },
        React.createElement(Box, { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 1 },
            React.createElement(Box, { flexDirection: "row", alignItems: "center" },
                React.createElement(Text, { color: theme.colors.status.info, bold: true },
                    "[FILE EXPLORER]",
                    ' '),
                React.createElement(Text, { color: theme.colors.text.bright, bold: true }, currentPath ? `./${currentPath}` : './ (workspace root)')),
            React.createElement(Text, { color: theme.colors.text.muted }, "\u2191/\u2193 navigate \u00B7 \u2192/Enter enter \u00B7 \u2190 back \u00B7 Esc exit")),
        searchQuery && (React.createElement(Box, { flexDirection: "row", marginBottom: 1 },
            React.createElement(Text, { color: theme.colors.text.muted }, "Search filter: "),
            React.createElement(Text, { color: theme.colors.status.success, bold: true }, searchQuery))),
        React.createElement(Box, { flexDirection: "row", marginBottom: 1, borderStyle: "single", borderColor: theme.colors.code.border },
            React.createElement(Box, { width: 2, flexShrink: 0 }),
            React.createElement(Box, { width: 7, flexShrink: 0 },
                React.createElement(Text, { color: theme.colors.text.muted, bold: true }, "TYPE")),
            React.createElement(Box, { width: 24, flexShrink: 0 },
                React.createElement(Text, { color: theme.colors.text.muted, bold: true }, "NAME")),
            React.createElement(Box, { width: 10, flexShrink: 0 },
                React.createElement(Text, { color: theme.colors.text.muted, bold: true }, "SIZE")),
            React.createElement(Box, { width: 14, flexShrink: 0 },
                React.createElement(Text, { color: theme.colors.text.muted, bold: true }, "MODIFIED")),
            React.createElement(Box, { flexShrink: 1 },
                React.createElement(Text, { color: theme.colors.text.muted, bold: true }, "KIND"))),
        React.createElement(FileList, { items: items, activeIndex: activeIndex, currentPath: currentPath })));
};
