import { Box, Text } from 'ink';
import React from 'react';
import { getToolStepPrimaryParam, getToolVerbLabel, SHELL_TOOL_SET } from '../../../constants/toolDisplay';
import { useTheme } from '../../../theme/ThemeContext';
import type { ToolCallEvent, ToolResultEvent, ToolStepEvent } from '../../../types/scenario';
import { truncateEnd } from '../../../utils/text';
import type { EventRenderContext } from './componentRegistry';
import { ToolStepCard } from './ToolStepCard';

/**
 * Renders a raw tool_call/tool_result. These two kinds are normally folded into a
 * `tool_step` before they reach the renderer (pairToolEvents for live turns,
 * historyToTurns for history), so this block is the fallback path for an
 * unpaired sibling — not a second card implementation.
 */
interface ToolTraceBlockProps {
  event: ToolCallEvent | ToolResultEvent;
  context?: EventRenderContext;
}

function renderValue(val: unknown): string {
  if (val === null || val === undefined) return '';
  if (typeof val === 'string') return truncateEnd(val, 60);
  if (typeof val === 'number' || typeof val === 'boolean') return String(val);
  return truncateEnd(JSON.stringify(val), 60);
}

function toToolStepEvent(event: ToolCallEvent | ToolResultEvent): ToolStepEvent {
  if (event.kind === 'tool_call') {
    return {
      kind: 'tool_step',
      id: event.id,
      tool: event.tool,
      params: event.params,
      text: event.text,
      success: false,
      output: '',
      error: '',
      metadata: {},
      pending: true,
    };
  }
  return {
    kind: 'tool_step',
    id: event.id,
    tool: event.tool,
    params: (event.metadata?.params as Record<string, unknown>) || {},
    success: event.success,
    output: event.output,
    error: event.error,
    truncated: event.truncated,
    metadata: event.metadata,
    pending: false,
  };
}

export const ToolTraceBlock: React.FC<ToolTraceBlockProps> = React.memo(({ event, context }) => {
  const { theme } = useTheme();

  if (context?.isRunning || context?.isHistorical) {
    return <ToolStepCard event={toToolStepEvent(event)} context={context} />;
  }

  if (event.kind === 'tool_call') {
    const primary = getToolStepPrimaryParam(event.tool, event.params);
    return (
      <Box flexDirection="row" alignItems="center" width="100%" marginBottom={1} paddingX={1}>
        <Text color={theme.colors.text.dim}>→ </Text>
        <Text color={theme.colors.text.bright} bold>
          {getToolVerbLabel(event.tool)}
        </Text>
        {primary && (
          <>
            <Text color={theme.colors.text.dim}> </Text>
            <Text color={theme.colors.text.muted}>
              {primary.key}: {primary.value}
            </Text>
          </>
        )}
      </Box>
    );
  }

  const isShell = SHELL_TOOL_SET.has(event.tool.toLowerCase());
  const statusColor = isShell
    ? theme.colors.text.bright
    : event.success
      ? theme.colors.status.success
      : theme.colors.status.error;
  const statusGlyph = isShell ? '→' : event.success ? '' : '✗';
  const detail = event.error || (event.output ? renderValue(event.output) : '');
  return (
    <Box flexDirection="row" alignItems="center" width="100%" marginBottom={1} paddingX={1}>
      <Text color={statusColor} bold>
        {statusGlyph} {getToolVerbLabel(event.tool)}
      </Text>
      {detail && (
        <>
          <Text color={theme.colors.text.dim}> </Text>
          <Text color={theme.colors.text.muted} wrap="wrap">
            {detail}
          </Text>
        </>
      )}
    </Box>
  );
});
