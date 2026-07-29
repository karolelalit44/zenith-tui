import { Text } from 'ink';
import React from 'react';
import { useTheme } from '../../theme/ThemeContext';
export const ModalFooter = ({ shortcuts }) => {
    const { theme } = useTheme();
    return (React.createElement(Text, null, shortcuts.map((s, i) => (React.createElement(Text, { key: i },
        i > 0 && React.createElement(Text, null, " \u00B7 "),
        React.createElement(Text, { color: theme.colors.text.emerald }, s.key),
        " ",
        s.label)))));
};
