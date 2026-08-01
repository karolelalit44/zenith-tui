import { Box, Text, useInput } from 'ink';
import React, { useEffect, useState } from 'react';
import { ModalFooter } from '../../components/ui/ModalFooter';
import { RoundedBox } from '../../components/ui/RoundedBox';
import type { BudgetStatus, CostSummaryItem, TokenUsageStats } from '../../services/api/TokenUsageService';
import { tokenUsageService } from '../../services/api/TokenUsageService';
import { formatTokenCount } from '../../services/api/tokenEstimationService';
import { useTheme } from '../../theme/ThemeContext';

interface UsageModalProps {
  onClose: () => void;
}

function formatCost(cost: number): string {
  if (cost >= 1) return `$${cost.toFixed(2)}`;
  if (cost >= 0.01) return `$${cost.toFixed(4)}`;
  if (cost <= 0) return '$0.00';
  return `$${cost.toFixed(6)}`;
}

const UsageModal: React.FC<UsageModalProps> = ({ onClose }) => {
  const { theme } = useTheme();
  const [stats, setStats] = useState<TokenUsageStats | null>(null);
  const [costData, setCostData] = useState<CostSummaryItem[]>([]);
  const [budget, _setBudget] = useState<BudgetStatus | null>(null);
  const [period, _setPeriod] = useState<'all' | 'day' | 'week' | 'month'>('all');

  useInput((_char, key) => {
    if (key.escape || key.return) onClose();
  });

  useEffect(() => {
    tokenUsageService.fetchStats().then(setStats);
    tokenUsageService.fetchCostSummary(period).then(setCostData);
  }, [period]);

  const totals = stats?.totals;
  const models = stats?.models ?? [];

  const costBar =
    budget?.active && budget.max_monthly_cost
      ? Math.min(100, Math.round(((budget.monthly_cost ?? 0) / budget.max_monthly_cost) * 100))
      : 0;

  const totalBlocks = 15;
  const filledBlocks = Math.max(0, Math.min(totalBlocks, Math.round((costBar / 100) * totalBlocks)));
  const bar = '█'.repeat(filledBlocks) + '░'.repeat(totalBlocks - filledBlocks);

  return (
    <RoundedBox title="TOKEN USAGE & COSTS" borderColor={theme.colors.border.active} hasShadow>
      <Box flexDirection="column" paddingX={2} paddingY={1} width="100%">
        <Box flexDirection="row" justifyContent="space-between" marginBottom={1}>
          <Text color={theme.colors.text.emerald} bold>
            [USAGE STATISTICS]
          </Text>
          <Text color={theme.colors.text.muted}>Press Esc or Enter to close</Text>
        </Box>

        {totals && (
          <Box flexDirection="row" justifyContent="space-between" marginBottom={1}>
            <Box flexDirection="column" width="25%">
              <Text color={theme.colors.text.muted}>Total Tokens</Text>
              <Text color={theme.colors.text.bright} bold>
                {formatTokenCount(totals.grand_total_tokens)}
              </Text>
            </Box>
            <Box flexDirection="column" width="25%">
              <Text color={theme.colors.text.muted}>Total Cost</Text>
              <Text color={theme.colors.text.bright} bold>
                {formatCost(totals.grand_total_cost_usd)}
              </Text>
            </Box>
            <Box flexDirection="column" width="25%">
              <Text color={theme.colors.text.muted}>Requests</Text>
              <Text color={theme.colors.text.bright} bold>
                {totals.total_requests}
              </Text>
            </Box>
            <Box flexDirection="column" width="25%">
              <Text color={theme.colors.text.muted}>Models Used</Text>
              <Text color={theme.colors.text.bright} bold>
                {totals.unique_models}
              </Text>
            </Box>
          </Box>
        )}

        {budget?.active && budget.max_monthly_cost > 0 && (
          <Box flexDirection="column" marginBottom={1} paddingX={1}>
            <Text color={theme.colors.text.warning} bold>
              MONTHLY BUDGET
            </Text>
            <Box flexDirection="row" alignItems="center">
              <Text color={costBar > 80 ? theme.colors.status.error : theme.colors.status.success}>
                [{bar}] {costBar}%
              </Text>
              <Text color={theme.colors.text.muted}>
                {' '}
                {formatCost(budget.monthly_cost ?? 0)} / {formatCost(budget.max_monthly_cost)}
              </Text>
            </Box>
          </Box>
        )}

        <Box
          flexDirection="row"
          borderStyle="single"
          borderTop
          borderBottom
          borderLeft={false}
          borderRight={false}
          borderColor={theme.colors.border.muted}
        >
          <Box width={16}>
            <Text color={theme.colors.text.muted} bold>
              MODEL
            </Text>
          </Box>
          <Box width={10}>
            <Text color={theme.colors.text.muted} bold>
              TOKENS
            </Text>
          </Box>
          <Box width={10}>
            <Text color={theme.colors.text.muted} bold>
              REQS
            </Text>
          </Box>
          <Box width={10}>
            <Text color={theme.colors.text.muted} bold>
              COST
            </Text>
          </Box>
          <Box width={12}>
            <Text color={theme.colors.text.muted} bold>
              INPUT/OUTPUT
            </Text>
          </Box>
        </Box>

        {models.length === 0 ? (
          <Box paddingY={1}>
            <Text color={theme.colors.text.dim} italic>
              No usage data yet. Start a conversation to see token stats.
            </Text>
          </Box>
        ) : (
          models.map((m, i) => (
            <Box key={i} flexDirection="row" width="100%">
              <Box width={16}>
                <Text color={theme.colors.text.dim} wrap="truncate-end">
                  {m.model}
                </Text>
              </Box>
              <Box width={10}>
                <Text color={theme.colors.text.ethereal}>{formatTokenCount(m.total_tokens)}</Text>
              </Box>
              <Box width={10}>
                <Text color={theme.colors.text.ethereal}>{m.request_count}</Text>
              </Box>
              <Box width={10}>
                <Text color={theme.colors.text.ethereal}>{formatCost(m.total_cost_usd)}</Text>
              </Box>
              <Box width={12}>
                <Text color={theme.colors.text.dim}>
                  {formatTokenCount(m.total_input_tokens ?? m.total_prompt_tokens)}/
                  {formatTokenCount(m.total_output_tokens ?? m.total_completion_tokens)}
                </Text>
              </Box>
            </Box>
          ))
        )}

        {costData.length > 0 && (
          <>
            <Box marginTop={1} marginBottom={1}>
              <Text color={theme.colors.text.warning} bold underline>
                COST BY PERIOD
              </Text>
              <Text color={theme.colors.text.muted}> </Text>
              {(['all', 'day', 'week', 'month'] as const).map((p) => (
                <Text key={p} color={period === p ? theme.colors.text.bright : theme.colors.text.dim}>
                  {period === p ? ` [${p}] ` : ` ${p} `}
                </Text>
              ))}
            </Box>
            <Box
              flexDirection="row"
              borderStyle="single"
              borderTop
              borderBottom
              borderLeft={false}
              borderRight={false}
              borderColor={theme.colors.border.muted}
            >
              <Box width={16}>
                <Text color={theme.colors.text.muted} bold>
                  MODEL
                </Text>
              </Box>
              <Box width={10}>
                <Text color={theme.colors.text.muted} bold>
                  TOKENS
                </Text>
              </Box>
              <Box width={8}>
                <Text color={theme.colors.text.muted} bold>
                  REQ
                </Text>
              </Box>
              <Box width={10}>
                <Text color={theme.colors.text.muted} bold>
                  COST
                </Text>
              </Box>
            </Box>
            {costData.slice(0, 8).map((item, i) => (
              <Box key={i} flexDirection="row" width="100%">
                <Box width={16}>
                  <Text color={theme.colors.text.dim} wrap="truncate-end">
                    {item.model}
                  </Text>
                </Box>
                <Box width={10}>
                  <Text color={theme.colors.text.ethereal}>{formatTokenCount(item.total_tokens)}</Text>
                </Box>
                <Box width={8}>
                  <Text color={theme.colors.text.ethereal}>{item.requests}</Text>
                </Box>
                <Box width={10}>
                  <Text color={theme.colors.text.ethereal}>{formatCost(item.total_cost)}</Text>
                </Box>
              </Box>
            ))}
          </>
        )}

        <Box
          marginTop={1}
          paddingTop={1}
          borderStyle="single"
          borderTop
          borderBottom={false}
          borderLeft={false}
          borderRight={false}
          borderColor={theme.colors.border.muted}
        >
          <Text color={theme.colors.text.muted}>
            <ModalFooter
              shortcuts={[
                { key: 'd/w/m', label: 'filter period' },
                { key: '[Esc]', label: 'to close' },
              ]}
            />
          </Text>
        </Box>
      </Box>
    </RoundedBox>
  );
};

export default UsageModal;
