import { Box, Text } from 'ink';
import React, { useEffect, useState } from 'react';
import { useTerminalDimensions } from '../../hooks/useTerminalDimensions';
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
}

export const ComposerFooter: React.FC<ComposerFooterProps> = React.memo(
  ({ mode, modelFallback, providerName, dir, branch, totalTokens, effectiveMaxTokens }) => {
    const { theme } = useTheme();
    const { columns } = useTerminalDimensions();
    const [, forceUpdate] = useState(0);

    useEffect(() => modelStore.subscribe(() => forceUpdate((x) => x + 1)), []);

    const sel = modelStore.current;
    const chip = sel ? modelStore.toDisplayString(sel) : modelFallback;

    const layout = computeFooterLayout({
      columns,
      mode,
      chip,
      providerName,
      dir,
      branch,
      totalTokens,
      effectiveMaxTokens,
    });

    return (
      <Box flexDirection="row" width="100%" justifyContent="space-between" alignItems="center" flexWrap="nowrap">
        {/* Left Section: Mode label + Model chip + Provider */}
        <Box flexDirection="row" flexShrink={1} flexGrow={1} alignItems="center" overflow="hidden">
          <Text color={theme.colors.text.emerald} wrap="truncate-end">
            {layout.modeLabel}
          </Text>
          <Text color={theme.colors.status.accent} wrap="truncate-end">
            ◇ <Text color={theme.colors.text.muted}>{layout.chip}</Text>
          </Text>
          {layout.provider ? (
            <Text color={theme.colors.text.muted} wrap="truncate-end">
              {layout.provider}
            </Text>
          ) : null}
        </Box>

        {/* Right Section: folder:branch */}
        <Box flexDirection="row" flexShrink={0} alignItems="center" marginLeft={1}>
          {layout.dirText ? (
            <>
              <Text color={theme.colors.text.bright} wrap="truncate-end">
                {layout.dirText}
              </Text>
              {layout.branchText ? <Text color={theme.colors.text.muted}>:</Text> : null}
            </>
          ) : null}
          {layout.branchText ? (
            <Text color={theme.colors.text.emerald} wrap="truncate-end">
              {layout.branchText}{' '}
            </Text>
          ) : (
            <Text> </Text>
          )}
          <Text color={theme.colors.text.muted} wrap="truncate-end">
            {layout.tokenUsage}
          </Text>
        </Box>
      </Box>
    );
  },
);

ComposerFooter.displayName = 'ComposerFooter';
