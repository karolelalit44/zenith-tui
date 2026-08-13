import { Box, Text } from 'ink';
import React, { useEffect, useState } from 'react';
import { modelStore } from '../../services/providers/ModelStore';
import { useTheme } from '../../theme/ThemeContext';
import type { ContextCompactionFlowEvent, ScenarioMode } from '../../types/scenario';
import { computeFooterLayout } from '../../utils/footerLayout';
import { ContextIndicator } from './ContextIndicator';

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
  compaction?: ContextCompactionFlowEvent | null;
  /** Optional handler to open the compaction details overlay from the indicator. */
  onContextOpen?: () => void;
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
    compaction,
    onContextOpen,
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

        {/* Right Section: Running status + folder:branch + tokenUsage */}
        <Box flexDirection="row" flexShrink={0} alignItems="center" marginLeft={1}>
          {running ? (
            <Text color={theme.colors.status.warning} wrap="truncate-end">
              Esc cancel{' '}
            </Text>
          ) : null}
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
          <ContextIndicator
            percent={Math.round((totalTokens / effectiveMaxTokens) * 100) || 0}
            totalTokens={totalTokens}
            compaction={compaction}
            onOpen={onContextOpen}
          />
          <Text color={theme.colors.text.muted} wrap="truncate-end">
            {layout.tokenUsage}
          </Text>
        </Box>
      </Box>
    );
  },
);

ComposerFooter.displayName = 'ComposerFooter';
