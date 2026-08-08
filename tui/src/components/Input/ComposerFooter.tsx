import { Box, Text } from 'ink';
import React, { useEffect, useState } from 'react';
import { modelStore } from '../../services/providers/ModelStore';
import { useTheme } from '../../theme/ThemeContext';
import type { ScenarioMode } from '../../types/scenario';
import { computeFooterLayout } from '../../utils/footerLayout';
import { ComposerGauge } from './ComposerGauge';
import { RunningSpinner } from './RunningSpinner';

interface ComposerFooterProps {
  mode: ScenarioMode;
  modelFallback: string;
  providerName: string;
  dir: string;
  branch: string;
  totalTokens: number;
  effectiveMaxTokens: number;
  running: boolean;
  disabled: boolean;
  inputEmpty: boolean;
}

export const ComposerFooter: React.FC<ComposerFooterProps> = React.memo(
  ({
    mode,
    modelFallback,
    providerName,
    dir,
    branch,
    totalTokens,
    effectiveMaxTokens,
    running,
    disabled,
    inputEmpty,
  }) => {
    const { theme } = useTheme();
    const [, forceUpdate] = useState(0);

    useEffect(() => modelStore.subscribe(() => forceUpdate((x) => x + 1)), []);

    const sel = modelStore.current;
    const chip = sel ? modelStore.toDisplayString(sel) : modelFallback;

    const columns = process.stdout.columns ?? 80;
    const layout = computeFooterLayout({
      columns,
      mode,
      chip,
      providerName,
      dir,
      branch,
      totalTokens,
      effectiveMaxTokens,
      running,
      disabled,
      inputEmpty,
    });

    return (
      <Box flexDirection="row" width="100%" justifyContent="space-between" alignItems="center">
        <Box flexDirection="row" flexShrink={1} alignItems="center" overflow="hidden">
          <Text color={theme.colors.text.emerald}>{layout.modeLabel}</Text>
          <Text color={theme.colors.status.accent} wrap="truncate-end">
            ◇ <Text color={theme.colors.text.muted}>{layout.chip}</Text>
            <Text color={theme.colors.text.dim}> ▾</Text>
          </Text>
          {layout.provider ? <Text color={theme.colors.text.muted}>{layout.provider}</Text> : null}
        </Box>

        <Box flexDirection="row" flexShrink={0} alignItems="center">
          {layout.dir ? <Text color={theme.colors.text.ethereal}>{layout.dir}</Text> : null}
          {layout.branch ? <Text color={theme.colors.text.emerald}>{layout.branch}</Text> : null}
          <Text color={theme.colors.text.muted}> | </Text>
          <Text color={theme.colors.status.info}>{layout.tokenCount}</Text>
          <Text color={theme.colors.text.muted}>/</Text>
          <Text color={theme.colors.text.bright}>{layout.maxTokens}</Text>
          <Text color={theme.colors.text.muted}> tokens </Text>
          {layout.showGauge ? <ComposerGauge usedTokens={totalTokens} maxTokens={effectiveMaxTokens} /> : null}
          <Text color={theme.colors.text.muted}> | </Text>
          {running ? (
            <>
              <RunningSpinner color={theme.colors.status.success} />
              <Text color={theme.colors.status.warning}> Esc cancel</Text>
            </>
          ) : disabled ? (
            <Text color={theme.colors.text.muted}>Input disabled</Text>
          ) : (
            <Text color={inputEmpty ? theme.colors.text.muted : theme.colors.text.dim}>
              {inputEmpty ? '↵' : '↵ send'}
            </Text>
          )}
        </Box>
      </Box>
    );
  },
);

ComposerFooter.displayName = 'ComposerFooter';
