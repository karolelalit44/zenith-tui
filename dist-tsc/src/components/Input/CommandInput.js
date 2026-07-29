import { Box, Text } from 'ink';
import React from 'react';
import { SESSION_STATUS_DEFAULTS } from '../../constants/statusDefaults';
import { useProvider } from '../../hooks/useProvider';
import { formatTokenCount } from '../../services/data/tokenEstimationService';
import { getActiveGitBranch } from '../../services/gitService';
import { useTheme } from '../../theme/ThemeContext';
import { MultiLineTextInput } from './MultiLineTextInput';
export const CommandInput = React.memo(({ input, onInputChange, onSubmit, disabled = false, attachments, onRemoveAttachment: _onRemoveAttachment, historyUp, historyDown, mode = 'build', totalTokens = 0, maxTokens = SESSION_STATUS_DEFAULTS.maxTokens, isRunning = false, tokenUsageStats, workspaceName = SESSION_STATUS_DEFAULTS.workspaceName, gitBranch, }) => {
    const { theme } = useTheme();
    const { activeProvider } = useProvider();
    const activeBranch = gitBranch || getActiveGitBranch();
    const modelShort = activeProvider.config.model || activeProvider.meta.defaultModel || 'unknown';
    const providerName = activeProvider.meta.name || 'Unknown';
    const modeLabel = mode === 'plan' ? '[PLAN]' : '[BUILD]';
    const modeColor = theme.colors.text.emerald;
    const columns = process.stdout.columns ?? 80;
    const isSmall = columns < 65;
    const isMedium = columns < 100;
    const contextPercent = Math.min(100, Math.round((totalTokens / maxTokens) * 100));
    const totalBlocks = 10;
    const filledBlocks = Math.max(0, Math.min(totalBlocks, Math.round((contextPercent / 100) * totalBlocks)));
    const contextGauge = '█'.repeat(filledBlocks) + '░'.repeat(totalBlocks - filledBlocks);
    const dirParts = workspaceName.replace(/\\/g, '/').split('/');
    const shortDir = dirParts.length > 2 ? `.../${dirParts.slice(-2).join('/')}` : workspaceName;
    const grandTotal = tokenUsageStats?.totals?.grand_total_tokens ?? 0;
    const requestCount = tokenUsageStats?.totals?.total_requests ?? 0;
    const dividerWidth = Math.max(0, columns - 6);
    return (React.createElement(Box, { flexDirection: "column", width: "100%", marginTop: 1 },
        attachments && attachments.length > 0 && (React.createElement(Box, { flexDirection: "row", flexWrap: "wrap", marginBottom: 0 }, attachments.map((att, idx) => (React.createElement(Box, { key: idx, flexDirection: "row", marginRight: 1 },
            React.createElement(Text, { color: theme.colors.status.info }, "[ATTACH]"),
            React.createElement(Text, { color: theme.colors.text.ethereal },
                " ",
                att.name),
            React.createElement(Text, { color: theme.colors.text.muted }, " "),
            React.createElement(Text, { color: theme.colors.status.error },
                "(#",
                idx + 1,
                ")")))))),
        React.createElement(Box, { flexDirection: "column", width: "100%", borderStyle: "round", borderColor: disabled ? theme.colors.border.muted : theme.colors.border.active, paddingX: 1, paddingY: 0 },
            React.createElement(Box, { flexDirection: "row", width: "100%", alignItems: "flex-start" },
                React.createElement(Text, { color: disabled ? theme.colors.text.muted : theme.colors.text.emerald, bold: true },
                    disabled ? '◌' : '❯',
                    ' '),
                React.createElement(Box, { flexDirection: "column", flexGrow: 1 }, disabled ? (React.createElement(Box, { flexDirection: "row", alignItems: "center", minHeight: 1 },
                    React.createElement(Text, { color: theme.colors.text.muted, italic: true }, "Processing... (Esc to cancel)"))) : (React.createElement(MultiLineTextInput, { value: input, onChange: onInputChange, onSubmit: onSubmit, placeholder: "Ask anything...", focus: !disabled, historyUp: historyUp, historyDown: historyDown })))),
            React.createElement(Box, { width: "100%", marginY: 0 },
                React.createElement(Text, { color: theme.colors.border.muted, wrap: "truncate-end" }, '─'.repeat(dividerWidth))),
            React.createElement(Box, { flexDirection: "row", width: "100%", justifyContent: "space-between", alignItems: "center" },
                React.createElement(Box, { flexDirection: "row", flexShrink: 1 },
                    React.createElement(Text, { color: modeColor },
                        modeLabel,
                        " "),
                    React.createElement(Text, { color: theme.colors.status.accent }, "\u25C7 "),
                    React.createElement(Text, { color: theme.colors.text.muted, wrap: "truncate-end" },
                        modelShort,
                        !isSmall ? ` · ${providerName}` : '')),
                React.createElement(Box, { flexDirection: "row", flexShrink: 0, alignItems: "center" },
                    !isMedium && React.createElement(Text, { color: theme.colors.text.ethereal }, shortDir),
                    activeBranch ? (React.createElement(React.Fragment, null,
                        !isMedium && React.createElement(Text, { color: theme.colors.text.muted }, " "),
                        React.createElement(Text, { color: theme.colors.text.emerald },
                            "(",
                            activeBranch,
                            ")"))) : null,
                    React.createElement(Text, { color: theme.colors.text.muted }, " | "),
                    React.createElement(Text, { color: theme.colors.status.info }, formatTokenCount(totalTokens)),
                    React.createElement(Text, { color: theme.colors.text.muted }, "/"),
                    React.createElement(Text, { color: grandTotal > 0 ? theme.colors.text.bright : theme.colors.text.muted }, formatTokenCount(grandTotal)),
                    React.createElement(Text, { color: theme.colors.text.muted }, " tokens "),
                    React.createElement(Text, { color: contextPercent > 80 ? theme.colors.status.warning : theme.colors.status.success },
                        "[",
                        contextGauge,
                        "] ",
                        contextPercent,
                        "%"),
                    requestCount > 0 && (React.createElement(React.Fragment, null,
                        React.createElement(Text, { color: theme.colors.text.muted }, " | "),
                        React.createElement(Text, { color: theme.colors.text.muted },
                            requestCount,
                            " req"))),
                    React.createElement(Text, { color: theme.colors.text.muted }, " | "),
                    isRunning ? (React.createElement(Text, { color: theme.colors.status.success, bold: true }, "Running")) : (React.createElement(Text, { color: theme.colors.text.muted }, "Idle")))))));
});
