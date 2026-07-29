import { Box, Text } from 'ink';
import React from 'react';
import { SESSION_STATUS_DEFAULTS } from '../../constants/statusDefaults';
import { useProvider } from '../../hooks/useProvider';
import { formatTokenCount } from '../../services/data/tokenEstimationService';
import { getActiveGitBranch } from '../../services/gitService';
import { useTheme } from '../../theme/ThemeContext';
export const SessionStatusBar = ({ mode, totalTokens, maxTokens = SESSION_STATUS_DEFAULTS.maxTokens, isRunning = false, isOverlayOpen = false, hasEvents = false, modelName, workspaceName = SESSION_STATUS_DEFAULTS.workspaceName, gitBranch, tokenUsageStats, }) => {
    const { theme } = useTheme();
    const { activeProvider } = useProvider();
    const activeBranch = gitBranch || getActiveGitBranch();
    const _providerName = activeProvider.meta.name || 'Unknown';
    const _modelShort = modelName || activeProvider.config.model || activeProvider.meta.defaultModel || 'unknown';
    const contextPercent = Math.min(100, Math.round((totalTokens / maxTokens) * 100));
    const modeBadge = mode === 'plan'
        ? { label: '[PLAN]', color: theme.colors.text.emerald }
        : { label: '[BUILD]', color: theme.colors.text.emerald };
    const totalBlocks = 10;
    const filledBlocks = Math.max(0, Math.min(totalBlocks, Math.round((contextPercent / 100) * totalBlocks)));
    const contextGauge = '█'.repeat(filledBlocks) + '░'.repeat(totalBlocks - filledBlocks);
    const dirParts = workspaceName.replace(/\\/g, '/').split('/');
    const shortDir = dirParts.length > 2 ? `.../${dirParts.slice(-2).join('/')}` : workspaceName;
    const grandTotal = tokenUsageStats?.totals?.grand_total_tokens ?? 0;
    const grandTotalCost = tokenUsageStats?.totals?.grand_total_cost_usd ?? 0;
    const requestCount = tokenUsageStats?.totals?.total_requests ?? 0;
    const formatCost = (cost) => {
        if (cost >= 1)
            return `$${cost.toFixed(2)}`;
        if (cost >= 0.01)
            return `$${cost.toFixed(4)}`;
        if (cost <= 0)
            return '';
        return `$${cost.toFixed(6)}`;
    };
    return (React.createElement(Box, { flexDirection: "column", width: "100%", marginTop: 1 },
        React.createElement(Box, { width: "100%" },
            React.createElement(Text, { color: theme.colors.border.muted }, '─'.repeat(Math.min(process.stdout.columns ?? 80, 80)))),
        React.createElement(Box, { flexDirection: "row", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap" },
            React.createElement(Box, { flexDirection: "row", alignItems: "center" },
                React.createElement(Box, { paddingX: 1, backgroundColor: modeBadge.color },
                    React.createElement(Text, { color: theme.colors.bg.app, bold: true }, modeBadge.label)),
                React.createElement(Text, { color: theme.colors.text.muted }, " "),
                isRunning ? (React.createElement(Text, { color: theme.colors.text.dim }, "Ctrl+C cancel \u00B7 Shift+T thinking")) : isOverlayOpen ? (React.createElement(Text, { color: theme.colors.text.dim }, "Esc close")) : hasEvents ? (React.createElement(Text, { color: theme.colors.text.dim }, "Ctrl+S save \u00B7 Ctrl+L clear \u00B7 Ctrl+P help")) : (React.createElement(Text, { color: theme.colors.text.dim }, "Enter send \u00B7 / commands"))),
            React.createElement(Box, { flexDirection: "row", alignItems: "center" },
                React.createElement(Text, { color: theme.colors.text.ethereal }, shortDir),
                activeBranch ? (React.createElement(React.Fragment, null,
                    React.createElement(Text, { color: theme.colors.text.muted }, " "),
                    React.createElement(Text, { color: theme.colors.text.emerald }, "("),
                    React.createElement(Text, { color: theme.colors.text.emerald }, activeBranch),
                    React.createElement(Text, { color: theme.colors.text.emerald }, ")"))) : null,
                React.createElement(Text, { color: theme.colors.text.muted }, " | "),
                React.createElement(Text, { color: theme.colors.status.info }, formatTokenCount(totalTokens)),
                React.createElement(Text, { color: theme.colors.text.muted }, "/"),
                React.createElement(Text, { color: grandTotal > 0 ? theme.colors.text.bright : theme.colors.text.muted }, formatTokenCount(grandTotal)),
                React.createElement(Text, { color: theme.colors.text.muted }, " tokens"),
                grandTotalCost > 0 && (React.createElement(React.Fragment, null,
                    React.createElement(Text, { color: theme.colors.text.muted }, " "),
                    React.createElement(Text, { color: theme.colors.status.info }, formatCost(grandTotalCost)))),
                React.createElement(Text, { color: theme.colors.text.muted }, " "),
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
                isRunning ? (React.createElement(Text, { color: theme.colors.status.success, bold: true }, "Running")) : (React.createElement(Text, { color: theme.colors.text.muted }, "Idle"))))));
};
