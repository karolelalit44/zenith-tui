import { Box, Text } from 'ink';
import React from 'react';
import { ASCII_SPINNER_FRAMES } from '../../../constants/animation';
import { getToolStepPrimaryParam, getToolStepStatusText, getToolVerbLabel } from '../../../constants/toolDisplay';
import { useAnimationTick } from '../../../context/AnimationContext';
import { useTheme } from '../../../theme/ThemeContext';
import type { ToolStepEvent } from '../../../types/scenario';
import type { EventRenderContext } from './componentRegistry';

interface ToolStepCardProps {
  event: ToolStepEvent;
  context?: EventRenderContext;
}

export const ToolStepCard: React.FC<ToolStepCardProps> = React.memo(({ event, context }) => {
  const { theme } = useTheme();
  const isPending = event.pending && context?.isRunning && !context?.isHistorical;
  const tick = useAnimationTick();
  // elapsed is approximated from the global tick (same 100ms cadence)
  const elapsed = isPending ? tick : 0;

  const primary = getToolStepPrimaryParam(event.tool, event.params);

  const statusText = !isPending ? getToolStepStatusText(event) : '';
  const verb = getToolVerbLabel(event.tool);
  // The server emits a generic "Executing <tool>..." template with the raw tool
  // name. Use the verb label ("Create path: x" / "Run <cmd>") for both pending
  // and completed rows so they stay consistent with the status line.
  const isGenericTemplate = event.text != null && /^Executing\s+.+(?:\.\.\.|…)$/.test(event.text.trim());
  const hasTextHeader = Boolean(event.text) && !isGenericTemplate;
  const headerText = hasTextHeader ? event.text : `${verb}${primary ? ` ${primary.value}` : ''}`;

  const isShellCommand = ['bash', 'run_command', 'execute'].includes(event.tool.toLowerCase());
  const isGrepSearch = ['grep', 'grep_search', 'glob'].includes(event.tool.toLowerCase());
  const isFileRead = ['file_read', 'read_file'].includes(event.tool.toLowerCase());

  const cmdString = primary?.value ?? (event.params.command as string) ?? '';

  return (
    <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
      <Box flexDirection="row" alignItems="center">
        {isPending && (
          <Text color={theme.colors.status.info} bold>
            [{ASCII_SPINNER_FRAMES[tick % ASCII_SPINNER_FRAMES.length]}]{' '}
          </Text>
        )}
        {isShellCommand ? (
          <Text color={theme.colors.status.accent} bold>
            $ {cmdString || headerText}
          </Text>
        ) : isFileRead ? (
          <Text color={theme.colors.status.info}>→ Read {primary?.value || headerText}</Text>
        ) : isGrepSearch ? (
          <Text color={theme.colors.status.warning}>* Grep &quot;{primary?.value || ''}&quot;</Text>
        ) : (
          <>
            <Text color={theme.colors.text.dim}>● </Text>
            <Text color={theme.colors.text.bright} bold>
              {headerText}
            </Text>
          </>
        )}
        {isPending && <Text color={theme.colors.text.muted}> ({(elapsed / 10).toFixed(0)}s)</Text>}
      </Box>

      {/* Shell command output box with Click to expand */}
      {isShellCommand && statusText && (
        <Box flexDirection="column" paddingLeft={2} marginTop={0}>
          <Box flexDirection="column" backgroundColor={theme.colors.code.background} paddingX={1} paddingY={0}>
            <Text color={theme.colors.code.output}>{statusText}</Text>
          </Box>

          <Text color={theme.colors.text.dim} italic>
            Click to expand
          </Text>
        </Box>
      )}

      {!isShellCommand && !isPending && statusText && (
        <Box flexDirection="row" paddingLeft={1}>
          <Text color={event.success ? theme.colors.status.success : theme.colors.status.error}>{statusText}</Text>
        </Box>
      )}
    </Box>
  );
});
