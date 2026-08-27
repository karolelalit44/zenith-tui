import { Box, Text } from 'ink';
import React from 'react';
import { useTerminalDimensions } from '../../hooks/useTerminalDimensions';
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
  /** Cumulative run/API usage (telemetry); falls back to totalTokens when omitted. */
  runTokens?: number;
  /** True when the cumulative run usage is estimated, not provider-reported. */
  runEstimated?: boolean;
  /** Composed-context occupancy percent (0–100). Omitted → no gauge renders. */
  contextPercent?: number;
  /** True when the context-window denominator is a fallback estimate. */
  windowEstimated?: boolean;
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
    runTokens,
    runEstimated,
    contextPercent,
    windowEstimated,
  }) => {
    const { theme } = useTheme();
    const { columns } = useTerminalDimensions();

    const chip = modelFallback;

    const layout = computeFooterLayout({
      columns,
      mode,
      chip,
      providerName,
      dir,
      branch,
      totalTokens,
      effectiveMaxTokens,
      runTokens,
      runEstimated,
      contextPercent,
      windowEstimated,
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
            {layout.gauge}
            {layout.gauge && layout.tokenUsage ? ' ' : ''}
            {layout.tokenUsage}
          </Text>
        </Box>
      </Box>
    );
  },
);

ComposerFooter.displayName = 'ComposerFooter';
