import { Box, Text } from 'ink';
import React from 'react';
import { SESSION_STATUS_DEFAULTS } from '../../constants/statusDefaults';
import { useProvider } from '../../hooks/useProvider';
import { formatTokenCount } from '../../services/data/tokenEstimationService';
import { getActiveGitBranch } from '../../services/gitService';
import { useTheme } from '../../theme/ThemeContext';
import { MultiLineTextInput } from './MultiLineTextInput';
export const CommandInput = React.memo(({ input, onInputChange, onSubmit, disabled = false, attachments, onRemoveAttachment, historyUp, historyDown, totalTokens = 0, maxTokens = SESSION_STATUS_DEFAULTS.maxTokens, mode = 'build', }) => {
    const { theme } = useTheme();
    const { activeProvider } = useProvider();
    const branch = getActiveGitBranch();
    const modelShort = activeProvider.config.model || activeProvider.meta.defaultModel || 'unknown';
    const providerName = activeProvider.meta.name || 'Unknown';
    const contextPercent = Math.min(100, Math.round((totalTokens / maxTokens) * 100));
    const cwd = process.cwd();
    const dirParts = cwd.replace(/\\/g, '/').split('/');
    const shortDir = dirParts.length > 2 ? `.../${dirParts.slice(-2).join('/')}` : cwd;
    const modeLabel = mode === 'plan' ? '[PLAN]' : '[BUILD]';
    const modeColor = theme.colors.text.emerald;
    const columns = process.stdout.columns ?? 80;
    const isSmall = columns < 65;
    const isMedium = columns < 90;
    return (React.createElement(Box, { flexDirection: "column", width: "100%", borderStyle: "round", borderColor: disabled ? theme.colors.border.muted : theme.colors.border.active, paddingX: 1, paddingY: 0, marginTop: 1 },
        attachments && attachments.length > 0 && (React.createElement(Box, { flexDirection: "row", flexWrap: "wrap", marginBottom: 0 }, attachments.map((att, idx) => (React.createElement(Box, { key: idx, flexDirection: "row", marginRight: 1 },
            React.createElement(Text, { color: theme.colors.status.info }, "\uD83D\uDCCE"),
            React.createElement(Text, { color: theme.colors.text.ethereal },
                " ",
                att.name),
            React.createElement(Text, { color: theme.colors.text.muted }, " "),
            React.createElement(Text, { color: theme.colors.status.error },
                "(#",
                idx + 1,
                ")")))))),
        React.createElement(Box, { flexDirection: "row", alignItems: "flex-start" },
            React.createElement(Text, { color: disabled ? theme.colors.text.muted : theme.colors.text.emerald, bold: true },
                disabled ? '◌' : '❯',
                ' '),
            React.createElement(Box, { flexDirection: "column", flexGrow: 1 },
                disabled ? (React.createElement(Box, { flexDirection: "row", alignItems: "center", minHeight: 1 },
                    React.createElement(Text, { color: theme.colors.text.muted, italic: true }, "Processing... (Esc to cancel)"))) : (React.createElement(MultiLineTextInput, { value: input, onChange: onInputChange, onSubmit: onSubmit, placeholder: "Ask anything...", focus: !disabled, historyUp: historyUp, historyDown: historyDown })),
                React.createElement(Box, { flexDirection: "row", justifyContent: "space-between", marginTop: 1, width: "100%" },
                    React.createElement(Box, { flexDirection: "row", flexShrink: 1 },
                        React.createElement(Text, { color: modeColor },
                            modeLabel,
                            " "),
                        React.createElement(Text, { color: theme.colors.status.accent }, "\u25C7 "),
                        React.createElement(Text, { color: theme.colors.text.muted, wrap: "truncate-end" },
                            modelShort,
                            !isSmall ? ` · ${providerName}` : '')),
                    React.createElement(Box, { flexDirection: "row", flexShrink: 0, paddingLeft: 1 },
                        React.createElement(Text, { color: theme.colors.text.dim, wrap: "truncate-end" },
                            !isMedium ? `${shortDir} ` : '',
                            branch && !isSmall ? (React.createElement(React.Fragment, null,
                                React.createElement(Text, { color: theme.colors.text.emerald },
                                    "(",
                                    branch,
                                    ")"),
                                ' ')) : null,
                            formatTokenCount(totalTokens),
                            " tok ",
                            contextPercent,
                            "%")))))));
});
