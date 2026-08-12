import { Box, Text } from 'ink';
import React, { useEffect, useState } from 'react';
import { modelStore } from '../../services/providers/ModelStore';
import { useTheme } from '../../theme/ThemeContext';
import type { ScenarioMode } from '../../types/scenario';
import { computeFooterLayout } from '../../utils/footerLayout';

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
  tokenScope?: 'turn' | 'session';
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
    tokenScope,
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
      tokenScope,
    });

    return (
      <Box flexDirection="row" width="100%" justifyContent="space-between" alignItems="center">
        {/* Left Section: Mode label + Model chip + Provider */}
        <Box flexDirection="row" flexShrink={1} alignItems="center" overflow="hidden">
          <Text color={theme.colors.text.emerald}>{layout.modeLabel}</Text>
          <Text color={theme.colors.status.accent} wrap="truncate-end">
            ◇ <Text color={theme.colors.text.muted}>{layout.chip}</Text>
          </Text>
          {layout.provider ? <Text color={theme.colors.text.muted}>{layout.provider}</Text> : null}
        </Box>

        {/* Right Section: Running status + folder:branch + tokenUsage */}
        <Box flexDirection="row" flexShrink={0} alignItems="center">
          {running ? <Text color={theme.colors.status.warning}>Esc cancel </Text> : null}
          {layout.dirText ? (
            <>
              <Text color={theme.colors.text.bright}>{layout.dirText}</Text>
              {layout.branchText ? <Text color={theme.colors.text.muted}>:</Text> : null}
            </>
          ) : null}
          {layout.branchText ? <Text color={theme.colors.text.emerald}>{layout.branchText} </Text> : <Text> </Text>}
          <Text color={theme.colors.text.muted}>{layout.tokenUsage}</Text>
        </Box>
      </Box>
    );
  },
);

ComposerFooter.displayName = 'ComposerFooter';
