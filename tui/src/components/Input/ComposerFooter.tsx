import { Box, Text } from 'ink';
import React, { useEffect, useState } from 'react';
import { formatTokenCount } from '../../services/api/tokenEstimationService';
import { modelStore } from '../../services/providers/ModelStore';
import { useTheme } from '../../theme/ThemeContext';
import type { ScenarioMode } from '../../types/scenario';
import { ComposerGauge } from './ComposerGauge';
import { RunningSpinner } from './RunningSpinner';

interface ModelChipProps {
  fallback: string;
}

/** Subscribes to modelStore so model changes re-render only this chip. */
const ModelChip: React.FC<ModelChipProps> = React.memo(({ fallback }) => {
  const { theme } = useTheme();
  const [, forceUpdate] = useState(0);

  useEffect(() => modelStore.subscribe(() => forceUpdate((x) => x + 1)), []);

  const sel = modelStore.current;
  const display = sel ? modelStore.toDisplayString(sel) : fallback;

  return (
    <Text color={theme.colors.status.accent}>
      ◇ <Text color={theme.colors.text.muted}>{display}</Text>
      <Text color={theme.colors.text.dim}> ▾</Text>
    </Text>
  );
});

ModelChip.displayName = 'ModelChip';

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

    const modeLabel = mode === 'plan' ? '[PLAN]' : '[BUILD]';
    const columns = process.stdout.columns ?? 80;
    const isSmall = columns < 65;
    const isMedium = columns < 100;

    return (
      <Box flexDirection="row" width="100%" justifyContent="space-between" alignItems="center">
        <Box flexDirection="row" flexShrink={1} alignItems="center">
          <Text color={theme.colors.text.emerald}>{modeLabel} </Text>
          <ModelChip fallback={modelFallback} />
          {!isSmall && providerName && <Text color={theme.colors.text.muted}> · {providerName}</Text>}
        </Box>

        <Box flexDirection="row" flexShrink={0} alignItems="center">
          {!isMedium && <Text color={theme.colors.text.ethereal}>{dir}</Text>}
          {branch ? (
            <>
              <Text color={theme.colors.text.muted}> </Text>
              <Text color={theme.colors.text.emerald}>({branch})</Text>
            </>
          ) : null}
          <Text color={theme.colors.text.muted}> | </Text>
          <Text color={theme.colors.status.info}>{formatTokenCount(totalTokens)}</Text>
          <Text color={theme.colors.text.muted}>/</Text>
          <Text color={theme.colors.text.bright}>{formatTokenCount(effectiveMaxTokens)}</Text>
          <Text color={theme.colors.text.muted}> tokens </Text>
          <ComposerGauge usedTokens={totalTokens} maxTokens={effectiveMaxTokens} />
          <Text color={theme.colors.text.muted}> | </Text>
          {running ? (
            <>
              <RunningSpinner color={theme.colors.status.success} />
              <Text color={theme.colors.status.warning}> Esc cancel</Text>
            </>
          ) : disabled ? (
            <Text color={theme.colors.text.muted}>Waiting for approval…</Text>
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
