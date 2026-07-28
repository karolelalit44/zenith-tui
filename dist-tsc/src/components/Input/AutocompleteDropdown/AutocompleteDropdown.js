import { Box, Text, useInput } from 'ink';
import React, { useState } from 'react';
import optionsData from '../../../services/data/options.json';
import { useTheme } from '../../../theme/ThemeContext';
const COMMAND_LIST = optionsData.commands;
export const AutocompleteDropdown = ({ input, onSelect, onClose }) => {
    const { theme } = useTheme();
    const [activeIndex, setActiveIndex] = useState(0);
    const cleanInput = input.startsWith('/') ? input : `/${input}`;
    const filtered = COMMAND_LIST.filter((c) => c.command.toLowerCase().includes(cleanInput.toLowerCase()));
    useInput((_char, key) => {
        if (filtered.length === 0)
            return;
        if (key.escape) {
            onClose();
        }
        else if (key.upArrow) {
            setActiveIndex((prev) => Math.max(0, prev - 1));
        }
        else if (key.downArrow) {
            setActiveIndex((prev) => Math.min(filtered.length - 1, prev + 1));
        }
        else if (key.return) {
            onSelect(filtered[activeIndex]?.command || '');
        }
    });
    if (filtered.length === 0) {
        return (React.createElement(Box, { flexDirection: "column", marginTop: 1, paddingX: 1 },
            React.createElement(Text, { color: theme.colors.text.muted }, "No matching slash commands.")));
    }
    return (React.createElement(Box, { flexDirection: "column", width: "100%", borderStyle: "round", borderColor: theme.colors.status.accent, paddingX: 1, paddingY: 1, marginTop: 1 },
        React.createElement(Box, { flexDirection: "row", alignItems: "center", marginBottom: 1 },
            React.createElement(Text, { color: theme.colors.status.accent, bold: true }, "[SLASH COMMANDS]"),
            React.createElement(Text, { color: theme.colors.text.muted }, " \u2014 Type to filter \u00B7 \u2191/\u2193 navigate \u00B7 Enter select \u00B7 Esc back")),
        filtered.map((cmd, i) => {
            const isActive = i === activeIndex;
            return (React.createElement(Box, { key: i, flexDirection: "row", alignItems: "center" },
                React.createElement(Box, { width: 2, flexShrink: 0 },
                    React.createElement(Text, { color: isActive ? theme.colors.status.success : theme.colors.text.muted }, isActive ? '▸' : ' ')),
                React.createElement(Box, { width: 16, flexShrink: 0 },
                    React.createElement(Text, { color: isActive ? theme.colors.status.info : theme.colors.text.bright, bold: isActive }, cmd.command)),
                React.createElement(Box, { flexShrink: 1 },
                    React.createElement(Text, { color: isActive ? theme.colors.text.bright : theme.colors.text.muted }, cmd.description))));
        })));
};
