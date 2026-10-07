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
  /** Cumulative run/API usage (telemetry). */
  runTokens?: number;
  /** Composed-context occupancy percent (0–100). Omitted → no gauge renders. */
  contextPercent?: number;
  /** Whether Calm Mode is active. **/
  calmMode?: boolean;
}

export const ComposerFooter: React.FC<ComposerFooterProps> = React.memo(
  ({ mode, modelFallback, providerName, dir, branch, runTokens, contextPercent, calmMode }) => {
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
      runTokens,
      contextPercent,
      calmMode,
    });

    const showChip = layout.chip.length > 0;
    const showRight = Boolean(layout.dirText || layout.branchText || layout.calmLabel || layout.tokenUsage);

    return (
      <Box flexDirection="row" width="100%" justifyContent="space-between" alignItems="center" flexWrap="nowrap">
        {/* Left Section: Mode label + Model chip + Provider */}
        <Box flexDirection="row" flexShrink={1} flexGrow={1} alignItems="center" overflow="hidden">
          <Text color={theme.colors.text.emerald} wrap="truncate-end">
            {layout.modeLabel}
          </Text>
          {showChip ? (
            <Text color={theme.colors.status.accent} wrap="truncate-end">
              ◇ <Text color={theme.colors.text.muted}>{layout.chip}</Text>
            </Text>
          ) : null}
          {layout.provider ? (
            <Text color={theme.colors.text.muted} wrap="truncate-end">
              {layout.provider}
            </Text>
          ) : null}
        </Box>

        {/* Right Section: folder:branch */}
        {showRight ? (
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
            ) : null}
            {layout.calmLabel && (
              <Box marginRight={1}>
                <Text color={theme.colors.status.accent}>{layout.calmLabel}</Text>
              </Box>
            )}
            <Text color={theme.colors.text.muted} wrap="truncate-end">
              {layout.tokenUsage}
            </Text>
          </Box>
        ) : null}
      </Box>
    );
  },
);

ComposerFooter.displayName = 'ComposerFooter';
