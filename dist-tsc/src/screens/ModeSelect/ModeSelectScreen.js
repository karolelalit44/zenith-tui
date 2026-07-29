import { Box, Text, useInput } from 'ink';
import React, { useState } from 'react';
import { RoundedBox } from '../../components/ui/RoundedBox';
import { useTheme } from '../../theme/ThemeContext';
import { MODE_META, MODE_OPTIONS } from './data/modeData';
export const ModeSelectScreen = ({ currentMode, onSelect, onClose }) => {
    const { theme } = useTheme();
    const currentIdx = MODE_OPTIONS.findIndex((m) => m.id === currentMode);
    const [selectedIndex, setSelectedIndex] = useState(currentIdx >= 0 ? currentIdx : 1);
    useInput((_char, key) => {
        if (key.upArrow) {
            setSelectedIndex((prev) => Math.max(0, prev - 1));
        }
        if (key.downArrow) {
            setSelectedIndex((prev) => Math.min(MODE_OPTIONS.length - 1, prev + 1));
        }
        if (key.return) {
            onSelect(MODE_OPTIONS[selectedIndex].id);
        }
        if (key.escape) {
            onClose();
        }
    });
    return (React.createElement(RoundedBox, { title: MODE_META.title, borderColor: theme.colors.border.active, hasShadow: true },
        React.createElement(Box, { flexDirection: "column", paddingX: 2, paddingY: 1, width: "100%" },
            React.createElement(Box, { marginBottom: 1, paddingBottom: 1, borderStyle: "single", borderTop: false, borderLeft: false, borderRight: false, borderColor: theme.colors.border.muted },
                React.createElement(Text, { color: theme.colors.text.emerald }, "\u276F "),
                React.createElement(Text, { color: theme.colors.text.ethereal, bold: true }, MODE_META.headerLabel)),
            MODE_OPTIONS.map((mode, idx) => {
                const isSelected = idx === selectedIndex;
                const isCurrent = mode.id === currentMode;
                return (React.createElement(Box, { key: mode.id, flexDirection: "row", marginY: 1, width: "100%" },
                    React.createElement(Box, { width: 3 },
                        React.createElement(Text, { color: isSelected ? theme.colors.text.emerald : theme.colors.text.dim }, isSelected ? '▸ ' : '  ')),
                    React.createElement(Box, { flexDirection: "column", flexGrow: 1 },
                        React.createElement(Box, { flexDirection: "row", alignItems: "center" },
                            React.createElement(Text, { color: isSelected ? theme.colors.text.emerald : theme.colors.text.dim },
                                mode.icon,
                                " "),
                            React.createElement(Text, { color: isSelected ? theme.colors.text.ethereal : theme.colors.text.dim, bold: isSelected }, mode.label),
                            isCurrent && (React.createElement(Text, { color: isSelected ? theme.colors.text.muted : theme.colors.text.dim }, " (current)"))),
                        React.createElement(Box, { marginTop: 0, paddingLeft: 3 },
                            React.createElement(Text, { color: isSelected ? theme.colors.text.muted : theme.colors.text.dim, italic: isSelected }, mode.desc)))));
            }),
            React.createElement(Box, { marginTop: 1, paddingTop: 1, borderStyle: "single", borderTop: true, borderLeft: false, borderRight: false, borderBottom: false, borderColor: theme.colors.border.muted, justifyContent: "center" },
                React.createElement(Text, { color: theme.colors.text.muted },
                    React.createElement(Text, { color: theme.colors.text.emerald }, MODE_META.hotkeys.navigate),
                    ' ',
                    React.createElement(Text, { color: theme.colors.text.emerald }, MODE_META.hotkeys.select),
                    ' ',
                    React.createElement(Text, { color: theme.colors.text.emerald }, MODE_META.hotkeys.close))))));
};
