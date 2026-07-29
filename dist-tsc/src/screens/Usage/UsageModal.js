import { Box, Text, useInput } from 'ink';
import React, { useEffect, useState } from 'react';
import { ModalFooter } from '../../components/ui/ModalFooter';
import { RoundedBox } from '../../components/ui/RoundedBox';
import { tokenUsageService } from '../../services/data/TokenUsageService';
import { formatTokenCount } from '../../services/data/tokenEstimationService';
import { useTheme } from '../../theme/ThemeContext';
function formatCost(cost) {
    if (cost >= 1)
        return `$${cost.toFixed(2)}`;
    if (cost >= 0.01)
        return `$${cost.toFixed(4)}`;
    if (cost <= 0)
        return '$0.00';
    return `$${cost.toFixed(6)}`;
}
const UsageModal = ({ onClose }) => {
    const { theme } = useTheme();
    const [stats, setStats] = useState(null);
    const [costData, setCostData] = useState([]);
    const [budget, _setBudget] = useState(null);
    const [period, _setPeriod] = useState('all');
    useInput((_char, key) => {
        if (key.escape || key.return)
            onClose();
    });
    useEffect(() => {
        tokenUsageService.fetchStats().then(setStats);
        tokenUsageService.fetchCostSummary(period).then(setCostData);
    }, [period]);
    const totals = stats?.totals;
    const models = stats?.models ?? [];
    const costBar = budget?.active && budget.max_monthly_cost
        ? Math.min(100, Math.round(((budget.monthly_cost ?? 0) / budget.max_monthly_cost) * 100))
        : 0;
    const totalBlocks = 15;
    const filledBlocks = Math.max(0, Math.min(totalBlocks, Math.round((costBar / 100) * totalBlocks)));
    const bar = '█'.repeat(filledBlocks) + '░'.repeat(totalBlocks - filledBlocks);
    return (React.createElement(RoundedBox, { title: "TOKEN USAGE & COSTS", borderColor: theme.colors.border.active, hasShadow: true },
        React.createElement(Box, { flexDirection: "column", paddingX: 2, paddingY: 1, width: "100%" },
            React.createElement(Box, { flexDirection: "row", justifyContent: "space-between", marginBottom: 1 },
                React.createElement(Text, { color: theme.colors.text.emerald, bold: true }, "[USAGE STATISTICS]"),
                React.createElement(Text, { color: theme.colors.text.muted }, "Press Esc or Enter to close")),
            totals && (React.createElement(Box, { flexDirection: "row", justifyContent: "space-between", marginBottom: 1 },
                React.createElement(Box, { flexDirection: "column", width: "25%" },
                    React.createElement(Text, { color: theme.colors.text.muted }, "Total Tokens"),
                    React.createElement(Text, { color: theme.colors.text.bright, bold: true }, formatTokenCount(totals.grand_total_tokens))),
                React.createElement(Box, { flexDirection: "column", width: "25%" },
                    React.createElement(Text, { color: theme.colors.text.muted }, "Total Cost"),
                    React.createElement(Text, { color: theme.colors.text.bright, bold: true }, formatCost(totals.grand_total_cost_usd))),
                React.createElement(Box, { flexDirection: "column", width: "25%" },
                    React.createElement(Text, { color: theme.colors.text.muted }, "Requests"),
                    React.createElement(Text, { color: theme.colors.text.bright, bold: true }, totals.total_requests)),
                React.createElement(Box, { flexDirection: "column", width: "25%" },
                    React.createElement(Text, { color: theme.colors.text.muted }, "Models Used"),
                    React.createElement(Text, { color: theme.colors.text.bright, bold: true }, totals.unique_models)))),
            budget?.active && budget.max_monthly_cost > 0 && (React.createElement(Box, { flexDirection: "column", marginBottom: 1, paddingX: 1 },
                React.createElement(Text, { color: theme.colors.text.warning, bold: true }, "MONTHLY BUDGET"),
                React.createElement(Box, { flexDirection: "row", alignItems: "center" },
                    React.createElement(Text, { color: costBar > 80 ? theme.colors.status.error : theme.colors.status.success },
                        "[",
                        bar,
                        "] ",
                        costBar,
                        "%"),
                    React.createElement(Text, { color: theme.colors.text.muted },
                        ' ',
                        formatCost(budget.monthly_cost ?? 0),
                        " / ",
                        formatCost(budget.max_monthly_cost))))),
            React.createElement(Box, { flexDirection: "row", borderStyle: "single", borderTop: true, borderBottom: true, borderLeft: false, borderRight: false, borderColor: theme.colors.border.muted },
                React.createElement(Box, { width: 16 },
                    React.createElement(Text, { color: theme.colors.text.muted, bold: true }, "MODEL")),
                React.createElement(Box, { width: 10 },
                    React.createElement(Text, { color: theme.colors.text.muted, bold: true }, "TOKENS")),
                React.createElement(Box, { width: 10 },
                    React.createElement(Text, { color: theme.colors.text.muted, bold: true }, "REQS")),
                React.createElement(Box, { width: 10 },
                    React.createElement(Text, { color: theme.colors.text.muted, bold: true }, "COST")),
                React.createElement(Box, { width: 12 },
                    React.createElement(Text, { color: theme.colors.text.muted, bold: true }, "INPUT/OUTPUT"))),
            models.length === 0 ? (React.createElement(Box, { paddingY: 1 },
                React.createElement(Text, { color: theme.colors.text.dim, italic: true }, "No usage data yet. Start a conversation to see token stats."))) : (models.map((m, i) => (React.createElement(Box, { key: i, flexDirection: "row", width: "100%" },
                React.createElement(Box, { width: 16 },
                    React.createElement(Text, { color: theme.colors.text.dim, wrap: "truncate-end" }, m.model)),
                React.createElement(Box, { width: 10 },
                    React.createElement(Text, { color: theme.colors.text.ethereal }, formatTokenCount(m.total_tokens))),
                React.createElement(Box, { width: 10 },
                    React.createElement(Text, { color: theme.colors.text.ethereal }, m.request_count)),
                React.createElement(Box, { width: 10 },
                    React.createElement(Text, { color: theme.colors.text.ethereal }, formatCost(m.total_cost_usd))),
                React.createElement(Box, { width: 12 },
                    React.createElement(Text, { color: theme.colors.text.dim },
                        formatTokenCount(m.total_input_tokens ?? m.total_prompt_tokens),
                        "/",
                        formatTokenCount(m.total_output_tokens ?? m.total_completion_tokens))))))),
            costData.length > 0 && (React.createElement(React.Fragment, null,
                React.createElement(Box, { marginTop: 1, marginBottom: 1 },
                    React.createElement(Text, { color: theme.colors.text.warning, bold: true, underline: true }, "COST BY PERIOD"),
                    React.createElement(Text, { color: theme.colors.text.muted }, " "),
                    ['all', 'day', 'week', 'month'].map((p) => (React.createElement(Text, { key: p, color: period === p ? theme.colors.text.bright : theme.colors.text.dim }, period === p ? ` [${p}] ` : ` ${p} `)))),
                React.createElement(Box, { flexDirection: "row", borderStyle: "single", borderTop: true, borderBottom: true, borderLeft: false, borderRight: false, borderColor: theme.colors.border.muted },
                    React.createElement(Box, { width: 16 },
                        React.createElement(Text, { color: theme.colors.text.muted, bold: true }, "MODEL")),
                    React.createElement(Box, { width: 10 },
                        React.createElement(Text, { color: theme.colors.text.muted, bold: true }, "TOKENS")),
                    React.createElement(Box, { width: 8 },
                        React.createElement(Text, { color: theme.colors.text.muted, bold: true }, "REQ")),
                    React.createElement(Box, { width: 10 },
                        React.createElement(Text, { color: theme.colors.text.muted, bold: true }, "COST"))),
                costData.slice(0, 8).map((item, i) => (React.createElement(Box, { key: i, flexDirection: "row", width: "100%" },
                    React.createElement(Box, { width: 16 },
                        React.createElement(Text, { color: theme.colors.text.dim, wrap: "truncate-end" }, item.model)),
                    React.createElement(Box, { width: 10 },
                        React.createElement(Text, { color: theme.colors.text.ethereal }, formatTokenCount(item.total_tokens))),
                    React.createElement(Box, { width: 8 },
                        React.createElement(Text, { color: theme.colors.text.ethereal }, item.requests)),
                    React.createElement(Box, { width: 10 },
                        React.createElement(Text, { color: theme.colors.text.ethereal }, formatCost(item.total_cost)))))))),
            React.createElement(Box, { marginTop: 1, paddingTop: 1, borderStyle: "single", borderTop: true, borderBottom: false, borderLeft: false, borderRight: false, borderColor: theme.colors.border.muted },
                React.createElement(Text, { color: theme.colors.text.muted },
                    React.createElement(ModalFooter, { shortcuts: [
                            { key: 'd/w/m', label: 'filter period' },
                            { key: '[Esc]', label: 'to close' },
                        ] }))))));
};
export default UsageModal;
