import { Box, Text } from 'ink';
import React from 'react';
import { ASCII_SPINNER_FRAMES } from '../../../constants/animation';
import { useAnimationTick } from '../../../context/AnimationContext';
import {
  getToolStepPrimaryParam,
  getToolStepStatusText,
  getToolVerbLabel,
  TOOL_STEP_PRIMARY_KEYS,
  TOOL_STEP_SKIP_PARAMS,
} from '../../../constants/toolDisplay';
import { useTheme } from '../../../theme/ThemeContext';
import type { ToolStepEvent } from '../../../types/scenario';
import type { EventRenderContext } from './componentRegistry';

interface ToolStepCardProps {
  event: ToolStepEvent;
  context?: EventRenderContext;
}

function formatValue(val: unknown): string {
  if (val === null || val === undefined) return 'null';
  if (typeof val === 'string') {
    if (val.length > 80) return `${val.slice(0, 77)}...`;
    return val;
  }
  if (typeof val === 'number' || typeof val === 'boolean') return String(val);
  const str = JSON.stringify(val);
  if (str.length > 80) return `${str.slice(0, 77)}...`;
  return str;
}

export const ToolStepCard: React.FC<ToolStepCardProps> = React.memo(({ event, context }) => {
  const { theme } = useTheme();
  const isPending = event.pending && context?.isRunning && !context?.isHistorical;
  const tick = useAnimationTick();
  // elapsed is approximated from the global tick (same 100ms cadence)
  const elapsed = isPending ? tick : 0;

  const primary = getToolStepPrimaryParam(event.tool, event.params);
  const detailEntries = Object.entries(event.params).filter(
    ([key]) =>
      !TOOL_STEP_SKIP_PARAMS.has(key.toLowerCase()) &&
      !TOOL_STEP_PRIMARY_KEYS.includes(key as (typeof TOOL_STEP_PRIMARY_KEYS)[number]),
  );

  const statusText = !isPending ? getToolStepStatusText(event) : '';
  const verb = getToolVerbLabel(event.tool);
  // The server emits a generic "Executing <tool>..." template with the raw tool
  // name. Use the verb label ("Create path: x" / "Run <cmd>") for both pending
  // and completed rows so they stay consistent with the status line.
  const isGenericTemplate =
    event.text != null && /^Executing\s+.+(?:\.\.\.|…)$/.test(event.text.trim());
  const hasTextHeader = Boolean(event.text) && !isGenericTemplate;
  const headerText = hasTextHeader
    ? event.text
    : `${verb}${primary ? ` ${primary.value}` : ''}`;

  return (
    <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
      <Box flexDirection="row" alignItems="center">
        <Text color={theme.colors.text.dim}>● </Text>
        {isPending && (
          <Text color={theme.colors.status.info} bold>
            [{ASCII_SPINNER_FRAMES[tick % ASCII_SPINNER_FRAMES.length]}]
          </Text>
        )}
        <Text color={theme.colors.text.bright} bold>
          {headerText}
        </Text>
        {hasTextHeader && primary && (
          <>
            <Text color={theme.colors.text.dim}> </Text>
            <Text color={theme.colors.text.muted}>
              {primary.key}: {primary.value}
            </Text>
          </>
        )}
        {isPending && <Text color={theme.colors.text.muted}> ({(elapsed / 10).toFixed(0)}s)</Text>}
      </Box>

      {isPending && detailEntries.length > 0 && (
        <Box flexDirection="column" paddingLeft={3}>
          {detailEntries.slice(0, 5).map(([key, val]) => (
            <Box key={key} flexDirection="row">
              <Text color={theme.colors.text.muted}>{key}: </Text>
              <Text color={theme.colors.text.ethereal} wrap="wrap">
                {formatValue(val)}
              </Text>
            </Box>
          ))}
        </Box>
      )}

      {!isPending && statusText && (
        <Box flexDirection="row" paddingLeft={1}>
          <Text color={event.success ? theme.colors.status.success : theme.colors.status.error}>{statusText}</Text>
        </Box>
      )}
    </Box>
  );
});
