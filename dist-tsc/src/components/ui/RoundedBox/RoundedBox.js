import { Box, Text } from 'ink';
import React from 'react';
import { useTheme } from '../../../theme/ThemeContext';
export const RoundedBox = ({ title, borderColor, children, paddingX = 1, paddingY = 0, hasShadow = false, }) => {
    const { theme } = useTheme();
    const currentBorderColor = borderColor || theme.colors.border.default;
    return (React.createElement(Box, { flexDirection: "column", width: "100%" },
        React.createElement(Box, { flexDirection: "row", width: "100%", position: "relative" },
            React.createElement(Box, { borderStyle: {
                    topLeft: '╭',
                    topRight: '╮',
                    top: '═',
                    bottom: '═',
                    bottomLeft: '╰',
                    bottomRight: '╯',
                    left: '║',
                    right: '║',
                }, borderColor: currentBorderColor, paddingX: paddingX, paddingY: paddingY, flexDirection: "column", flexGrow: 1 },
                React.createElement(Box, { flexDirection: "column", width: "100%", flexGrow: 1, justifyContent: "center" }, children)),
            title && (React.createElement(Box, { position: "absolute", top: 0, left: 0, width: "100%", justifyContent: "flex-end", paddingRight: 4 },
                React.createElement(Box, { flexDirection: "row" },
                    React.createElement(Text, { color: currentBorderColor }, "\u2563 "),
                    React.createElement(Text, { color: theme.colors.bg.app, backgroundColor: currentBorderColor, bold: true },
                        ' ',
                        title,
                        ' '),
                    React.createElement(Text, { color: currentBorderColor }, " \u2560")))),
            hasShadow && (React.createElement(Box, { flexDirection: "column", width: 1, paddingTop: 1 },
                React.createElement(Text, { color: theme.colors.shadow.ascii }, "\u2588"),
                React.createElement(Text, { color: theme.colors.shadow.ascii }, "\u2588"),
                React.createElement(Text, { color: theme.colors.shadow.ascii }, "\u2588"),
                React.createElement(Text, { color: theme.colors.shadow.ascii }, "\u2580"))))));
};
