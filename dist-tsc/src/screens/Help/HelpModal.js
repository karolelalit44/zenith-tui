import { Box, Text, useInput } from 'ink';
import React from 'react';
import { ModalFooter } from '../../components/ui/ModalFooter';
import { RoundedBox } from '../../components/ui/RoundedBox';
import { APP_VERSION } from '../../constants/app';
import { useTheme } from '../../theme/ThemeContext';
export const HelpModal = ({ onClose }) => {
    const { theme } = useTheme();
    useInput((_char, key) => {
        if (key.escape || key.return) {
            onClose();
        }
    });
    return (React.createElement(RoundedBox, { title: "ZENITH HELP & KEYBOARD SHORTCUTS", borderColor: theme.colors.border.active, hasShadow: true },
        React.createElement(Box, { flexDirection: "column", paddingX: 2, paddingY: 1, width: "100%" },
            React.createElement(Box, { marginBottom: 1, flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
                React.createElement(Text, { color: theme.colors.text.emerald, bold: true }, "[HELP & CLI WORKFLOW GUIDE]"),
                React.createElement(Text, { color: theme.colors.text.muted }, "Press Esc or Enter to close")),
            React.createElement(Box, { flexDirection: "row", width: "100%", justifyContent: "space-between" },
                React.createElement(Box, { flexDirection: "column", width: "30%" },
                    React.createElement(Text, { color: theme.colors.text.warning, bold: true, underline: true }, "KEYBOARD SHORTCUTS"),
                    React.createElement(Box, { marginTop: 1, flexDirection: "column" },
                        React.createElement(Box, { flexDirection: "row" },
                            React.createElement(Text, { color: theme.colors.status.info, bold: true }, "Shift + M"),
                            React.createElement(Text, { color: theme.colors.text.muted }, " Switch Mode")),
                        React.createElement(Box, { flexDirection: "row" },
                            React.createElement(Text, { color: theme.colors.status.info, bold: true }, "Ctrl + S"),
                            React.createElement(Text, { color: theme.colors.text.muted }, " Save Plan")),
                        React.createElement(Box, { flexDirection: "row" },
                            React.createElement(Text, { color: theme.colors.status.info, bold: true }, "Shift + T"),
                            React.createElement(Text, { color: theme.colors.text.muted }, " Toggle Thinking")),
                        React.createElement(Box, { flexDirection: "row" },
                            React.createElement(Text, { color: theme.colors.status.info, bold: true }, "Esc"),
                            React.createElement(Text, { color: theme.colors.text.muted }, " Cancel / Exit")),
                        React.createElement(Box, { flexDirection: "row" },
                            React.createElement(Text, { color: theme.colors.status.info, bold: true }, "@"),
                            React.createElement(Text, { color: theme.colors.text.muted }, " File Picker")),
                        React.createElement(Box, { flexDirection: "row" },
                            React.createElement(Text, { color: theme.colors.status.info, bold: true }, "/"),
                            React.createElement(Text, { color: theme.colors.text.muted }, " Command Palette")))),
                React.createElement(Box, { width: 1 },
                    React.createElement(Text, { color: theme.colors.border.muted }, "\u2502")),
                React.createElement(Box, { flexDirection: "column", width: "34%" },
                    React.createElement(Text, { color: theme.colors.text.warning, bold: true, underline: true }, "SLASH COMMANDS"),
                    React.createElement(Box, { marginTop: 1, flexDirection: "column" },
                        React.createElement(Text, { color: theme.colors.text.ethereal },
                            React.createElement(Text, { color: theme.colors.status.success }, "/provider"),
                            " AI Provider Management"),
                        React.createElement(Text, { color: theme.colors.text.ethereal },
                            React.createElement(Text, { color: theme.colors.status.success }, "/settings"),
                            " Theme & Options"),
                        React.createElement(Text, { color: theme.colors.text.ethereal },
                            React.createElement(Text, { color: theme.colors.status.success }, "/context"),
                            " View Context Window"),
                        React.createElement(Text, { color: theme.colors.text.ethereal },
                            React.createElement(Text, { color: theme.colors.status.success }, "/clear"),
                            " Reset Conversation"),
                        React.createElement(Text, { color: theme.colors.text.ethereal },
                            React.createElement(Text, { color: theme.colors.status.success }, "/compact"),
                            " Compress History"))),
                React.createElement(Box, { width: 1 },
                    React.createElement(Text, { color: theme.colors.border.muted }, "\u2502")),
                React.createElement(Box, { flexDirection: "column", width: "32%" },
                    React.createElement(Text, { color: theme.colors.text.warning, bold: true, underline: true }, "OPERATING MODES"),
                    React.createElement(Box, { marginTop: 1, flexDirection: "column" },
                        React.createElement(Text, { color: theme.colors.status.accent, bold: true }, "[PLAN MODE]"),
                        React.createElement(Text, { color: theme.colors.text.muted }, "Generates architectural roadmaps and saves to zenith_plans/ (created on first save)."),
                        React.createElement(Box, { marginTop: 1 },
                            React.createElement(Text, { color: theme.colors.status.success, bold: true }, "[BUILD MODE]")),
                        React.createElement(Text, { color: theme.colors.text.muted }, "Executes code generation, tests, and terminal build steps.")))),
            React.createElement(Box, { marginTop: 1, paddingTop: 1, borderStyle: "single", borderTop: true, borderBottom: false, borderLeft: false, borderRight: false, borderColor: theme.colors.border.muted, justifyContent: "center" },
                React.createElement(Text, { color: theme.colors.text.muted },
                    "Zenith TUI v",
                    APP_VERSION,
                    " \u00B7 ",
                    React.createElement(ModalFooter, { shortcuts: [{ key: '[Esc]', label: 'to return to prompt' }] }))))));
};
